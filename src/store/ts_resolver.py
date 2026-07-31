import re
from typing import List

from src.logger import get_logger

log = get_logger("ts_resolver")

# Obergrenze für die Gesamtzahl an Zeichen, die eine einzelne Auflösung erzeugen
# darf. Diamant-förmige Typgraphen (ein Typ referenziert denselben Sub-Typ
# mehrfach — z.B. Stripe) expandieren zu einem flachen String *exponentiell*,
# ganz ohne echten Zyklus und unabhängig von der Rekursionstiefe: Auf jeder
# Ebene wird die Sub-Expansion dupliziert. Kein Tiefenlimit und keine
# String-Memoisierung kann das verhindern — das voll expandierte Ergebnis ist
# selbst exponentiell groß. Wir begrenzen daher direkt die erzeugte Ausgabe:
# Ist das Budget erschöpft, bleiben weitere Custom-Typen als nackter Name
# stehen (wie zyklische Typen), statt Velorum mit >100 GB RAM zu sprengen.
#
# Die aufgelöste Signatur wird anschließend eingebettet/an externe LLM-Dienste
# geschickt. Dort zählt nicht die Byte-, sondern die *Token*-Grenze: Das Modell
# hat 131 072 Token Kontext, wovon ~50 000 für die Ausgabe reserviert sind — es
# bleiben also nur ~80 000 Token fürs gesamte Prompt, in dem die Signatur nur
# ein Feld unter mehreren ist. Diese Signaturen tokenisieren grob 1:1 zu Zeichen.
# 8 000 Zeichen (Worst Case ~16 000 an der Abschneide-Grenze) sind für jede real
# vorkommende Typ-Signatur großzügig und lassen reichlich Kontext für den Rest.
MAX_EXPANSION_CHARS = 8_000


def resolve_ts_signature(signature: str, type_defs: List[str]) -> str:
    # 1. Typ-Datenbank aufbauen
    # Wir extrahieren: Name, Generics (falls vorhanden) und den Body
    type_db = {}
    # Regex erkennt: type NAME<OPTIONAL_GENERIC> = BODY
    type_pattern = re.compile(r"type\s+(\w+)(?:<([^>]+)>)?\s*=\s*(.+)")

    for td in type_defs:
        match = type_pattern.search(td)
        if match:
            name, generics, body = match.groups()
            params = [p.strip() for p in generics.split(",")] if generics else []
            type_db[name] = {"params": params, "body": body.strip()}

    ident_pattern = re.compile(r"\w+")

    # 2. Erreichbarkeits-Graph aufbauen
    # Für jeden Typ die Menge aller transitiv erreichbaren Custom-Typen. Nur diese
    # können später — falls sie zugleich auf dem Expansions-Pfad liegen — eine
    # zyklische Rückwärtskante auslösen. Damit lässt sich pro Typ exakt bestimmen,
    # welche Vorfahren das Expansionsergebnis überhaupt beeinflussen können, was
    # eine korrekte Memoisierung ermöglicht (siehe `handle`).
    direct_refs = {
        name: {tok for tok in ident_pattern.findall(entry["body"]) if tok in type_db}
        for name, entry in type_db.items()
    }

    reachable = {}
    for name in type_db:
        seen = set()
        pending = [name]
        while pending:
            cur = pending.pop()
            for ref in direct_refs.get(cur, ()):
                if ref not in seen:
                    seen.add(ref)
                    pending.append(ref)
        reachable[name] = seen

    def smart_split(s):
        """Teilt Kommas nur auf der obersten Ebene (ignoriert Kommas in <...>)"""
        parts = []
        bracket_level = 0
        current = []
        for char in s:
            if char == '<':
                bracket_level += 1
            elif char == '>':
                bracket_level -= 1
            if char == ',' and bracket_level == 0:
                parts.append("".join(current).strip())
                current = []
            else:
                current.append(char)
        parts.append("".join(current).strip())
        return [p for p in parts if p]

    def match_generic(s, start):
        """Sucht ab `start` (das auf '<' zeigt) das balancierte schließende '>'.

        Liefert (args_raw, end_index) mit dem Index NACH dem '>', oder
        (None, start), falls die Klammerung nicht ausbalanciert ist. So werden
        beliebig tief verschachtelte Generics (z.B. `LIST<LIST<LIST<T>>>`)
        korrekt erfasst — was ein regulärer Ausdruck grundsätzlich nicht kann.
        """
        depth = 0
        i = start
        n = len(s)
        while i < n:
            if s[i] == '<':
                depth += 1
            elif s[i] == '>':
                depth -= 1
                if depth == 0:
                    return s[start + 1:i], i + 1
            i += 1
        return None, start

    # Memo für bereits expandierte Typen und Sammlung der erkannten Zyklen.
    # Der Memo-Key ist (name, relevante Vorfahren) — siehe `handle`.
    memo = {}
    cyclic_types = set()

    # Laufender Zähler der bereits produzierten Zeichen sowie ein Flag, ob wegen
    # Budget-Überschreitung abgeschnitten wurde. `produced` zählt jedes finale
    # Ausgabe-Zeichen genau einmal: Blätter beim Erzeugen, wiederverwendete
    # Memo-Treffer bei jeder erneuten Einsetzung (dort entsteht die Duplizierung
    # eines Diamant-Graphen). So spiegelt der Zähler die reale Ergebnisgröße.
    produced = 0
    truncated = False

    def resolve(target, stack):
        nonlocal produced, truncated
        # Wir scannen den String von links nach rechts, extrahieren Typ-Namen
        # (\w+) und – falls direkt ein '<' folgt – deren balancierte Generic-
        # Argumente. Alles Übrige (Klammern, Doppelpunkte, Kommas, Whitespace)
        # wird unverändert übernommen.
        out = []
        i = 0
        n = len(target)
        while i < n:
            # Budget erschöpft: Rest unverändert übernehmen, nicht weiter
            # expandieren. Verhindert, dass ein einzelner (breiter oder tief
            # verschachtelter) Body zu einem exponentiell großen String
            # zusammenwächst.
            if produced >= MAX_EXPANSION_CHARS:
                out.append(target[i:])
                truncated = True
                break

            m = ident_pattern.match(target, i)
            if not m:
                out.append(target[i])
                produced += 1
                i += 1
                continue

            name = m.group(0)
            j = m.end()
            args_raw = None
            if j < n and target[j] == '<':
                args_raw, end = match_generic(target, j)
                if args_raw is not None:
                    j = end

            out.append(handle(name, args_raw, stack))
            i = j

        return "".join(out)

    def handle(name, args_raw, stack):
        nonlocal produced, truncated

        # Primitiv oder nacktes Generic (kein Custom Type): unverändert lassen,
        # etwaige Argumente aber weiter auflösen.
        if name not in type_db:
            if args_raw is not None:
                resolved_args = ", ".join(resolve(a, stack) for a in smart_split(args_raw))
                return f"{name}<{resolved_args}>"
            produced += len(name)
            return name

        # Zyklus-Schutz: Typ verweist entlang des aktuellen Pfades auf sich selbst.
        # Nur echte Rekursion (der Typ liegt bereits auf dem aktuellen Pfad) wird
        # hier gestoppt und als Name unaufgelöst zurückgegeben.
        if name in stack:
            cyclic_types.add(name)
            if args_raw is not None:
                resolved_args = ", ".join(resolve(a, stack) for a in smart_split(args_raw))
                return f"{name}<{resolved_args}>"
            produced += len(name)
            return name

        # Budget erschöpft: nicht weiter expandieren, den Namen wie einen
        # zyklischen Typ unaufgelöst stehen lassen. Fängt Diamant-Graphen ab,
        # bei denen viele kleine Wiederverwendungen die Ausgabe aufblähen.
        if produced >= MAX_EXPANSION_CHARS:
            truncated = True
            if args_raw is not None:
                resolved_args = ", ".join(resolve(a, stack) for a in smart_split(args_raw))
                return f"{name}<{resolved_args}>"
            produced += len(name)
            return name

        entry = type_db[name]

        # Generic-Instanziierung: Argumente in den Body einsetzen. Da das Ergebnis
        # von den (auflösbaren) Argumenten abhängt, wird dieser seltene Fall NICHT
        # memoisiert — Korrektheit vor Geschwindigkeit.
        if args_raw is not None and entry["params"]:
            # Generic-Argumente ZUERST vollständig auflösen (mit dem aktuellen
            # Pfad, aber BEVOR `name` auf den Stack kommt), und erst danach in den
            # Body einsetzen. Nur echte Selbstverweise aus dem Body sollen einen
            # Zyklus auslösen.
            args = [resolve(a, stack) for a in smart_split(args_raw)]
            resolved_body = entry["body"]
            for param, arg in zip(entry["params"], args):
                # Nur ganze Wörter ersetzen (\b), Parameter escapen und das Argument
                # via Lambda einsetzen, damit `re.sub` Backslash-/Gruppen-Sequenzen
                # (z.B. `\1`) im Argument nicht als Regex-Referenzen interpretiert.
                resolved_body = re.sub(
                    rf"\b{re.escape(param)}\b", lambda _m, a=arg: a, resolved_body
                )
            return resolve(resolved_body, stack + (name,))

        # Memoisierung: Das Expansionsergebnis von `name` hängt vom aktuellen Pfad
        # NUR über jene Vorfahren ab, die von `name` aus erreichbar sind — denn nur
        # diese können eine zyklische Rückwärtskante schließen. Alle anderen
        # Vorfahren sind irrelevant. Als Key genügt daher (name, relevante Vorfahren),
        # was massive Wiederverwendung erlaubt und die exponentielle Neu-Expansion
        # stark verschachtelter Typen (z.B. Stripe) auf ~linear reduziert.
        relevant = frozenset(a for a in stack if a in reachable[name])
        key = (name, relevant)
        cached = memo.get(key)
        if cached is not None:
            # Wiederverwendung: Die Zeichen werden erneut in die Ausgabe kopiert
            # und zählen daher voll zum Budget — genau hier entsteht bei einem
            # Diamant-Graphen die Duplizierung.
            produced += len(cached)
            return cached

        # Frische Expansion: Die Blätter werden im rekursiven `resolve` gezählt;
        # `produced` hier NICHT erneut erhöhen (sonst würde Verschachtelung
        # doppelt gezählt).
        result = resolve(entry["body"], stack + (name,))
        memo[key] = result
        return result

    try:
        resolved = resolve(signature, ())
        if truncated:
            log.warning(
                "[resolve] Expansion exceeded %d chars — signature truncated "
                "(remaining custom types left unresolved) to avoid runaway "
                "memory. Signature starts with '%s'",
                MAX_EXPANSION_CHARS,
                signature[:80],
            )
        if cyclic_types:
            # Eine kompakte Sammel-Warnung statt einer riesigen Meldung pro Typ.
            log.warning(
                "[resolve] Left %d cyclic type reference(s) unresolved: %s",
                len(cyclic_types),
                ", ".join(sorted(cyclic_types)),
            )
        return resolved
    except RecursionError:
        # Letzte Verteidigungslinie: Sollte die Zyklus-Erkennung eine pathologische
        # Expansion doch einmal nicht abfangen, liefern wir die Original-Signatur
        # zurück, statt Velorum abstürzen zu lassen.
        log.error(
            f"[resolve] RecursionError while resolving signature — "
            f"returning original signature '{signature[:80]}'"
        )
        return signature
    except Exception as e:  # noqa: BLE001 - defensiv, darf den Prozess nie killen
        log.error(
            f"[resolve] Unexpected error ({type(e).__name__}: {e}) while resolving "
            f"signature — returning original signature '{signature[:80]}'"
        )
        return signature

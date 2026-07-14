import re
from typing import List


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

    def resolve(target, stack, warned_cycles=None):
        if warned_cycles is None:
            warned_cycles = set()

        # Finde den am weitesten links stehenden Typ-Namen, der evtl. <...> folgt
        # Wir suchen nach Wörtern, die nicht gefolgt werden von ( oder : (um Funktionsnamen zu schützen)
        pattern = r"\b(\w+)\b(?:<([^<>]+(?:<[^<>]+>)*)>)?"

        def replacement(match):
            name = match.group(1)
            args_raw = match.group(2)

            # Zyklus-Schutz: Typ verweist entlang des aktuellen Pfades auf sich selbst.
            # Wir lassen ihn unaufgelöst stehen, statt endlos weiter zu expandieren.
            if name in type_db and name in stack:
                if name not in warned_cycles:
                    warned_cycles.add(name)
                if args_raw:
                    resolved_args = ", ".join(
                        [resolve(a, stack, warned_cycles) for a in smart_split(args_raw)]
                    )
                    return f"{name}<{resolved_args}>"
                return name

            # Wenn der Name nicht in der DB ist, ist es ein Primitiv oder ein nacktes Generic
            if name not in type_db:
                if args_raw:
                    resolved_args = ", ".join(
                        [resolve(a, stack, warned_cycles) for a in smart_split(args_raw)]
                    )
                    return f"{name}<{resolved_args}>"
                return name

            entry = type_db[name]
            resolved_body = entry["body"]

            # Falls Generics im Spiel sind, ersetze diese im Body
            if args_raw and entry["params"]:
                args = smart_split(args_raw)
                for param, arg in zip(entry["params"], args):
                    # Wichtig: Nur ganze Wörter ersetzen (\b)
                    resolved_body = re.sub(rf"\b{param}\b", arg, resolved_body)

            # Rekursiv weiter auflösen, falls der Body selbst Custom Types enthält.
            # Der aktuelle Typ-Name kommt auf den Pfad-Stack, um Zyklen zu erkennen.
            return resolve(resolved_body, stack | {name}, warned_cycles)

        return re.sub(pattern, replacement, target)

    return resolve(signature, frozenset())

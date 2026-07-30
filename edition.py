import importlib.abc
import importlib.machinery
import importlib.util
import os
import sys

EDITION = os.getenv("EDITION", "ce")

# ce is src/ itself; ee and cloud entries are override layers on top
_OVERRIDE_CHAINS = {
    "ce": [],
    "ee": ["ee"],
    "cloud": ["cloud", "ee"],
}

_PACKAGES_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "packages")


class _EditionFinder(importlib.abc.MetaPathFinder):
    def find_spec(self, fullname, path, target=None):
        if not fullname.startswith("src.") or fullname == "src.edition":
            return None

        overrides = _OVERRIDE_CHAINS.get(EDITION, [])
        if not overrides:
            return None  # ce — normal src/ resolution handles everything

        rel = fullname[len("src."):].replace(".", os.sep)

        for edition in overrides:
            base = os.path.join(_PACKAGES_DIR, edition, "src")

            init = os.path.join(base, rel, "__init__.py")
            if os.path.exists(init):
                return importlib.util.spec_from_file_location(
                    fullname,
                    init,
                    submodule_search_locations=[os.path.join(base, rel)],
                )

            module = os.path.join(base, rel + ".py")
            if os.path.exists(module):
                return importlib.util.spec_from_file_location(fullname, module)

        # no override found — fall through to normal src/ resolution
        return None


def install():
    sys.meta_path.insert(0, _EditionFinder())

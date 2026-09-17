"""Build context: the document, its styles, formats and the name registry."""
from __future__ import annotations

from dataclasses import dataclass, field

import theme
import unohelp as U


@dataclass
class Ctx:
    doc: object
    fmt: dict = field(default_factory=dict)
    names: dict = field(default_factory=dict)
    cfg: object = None

    def setup(self):
        for name, props in theme.STYLES.items():
            U.make_style(self.doc, name, **{k: v for k, v in props.items() if v is not None})
        for key, code in theme.FORMATS.items():
            self.fmt[key] = U.number_format(self.doc, code)
        return self

    # -- convenience --------------------------------------------------
    def sheet(self, name, index=None):
        return U.sheet(self.doc, name, index)

    def name(self, key, sh_name, c1, r1, c2=None, r2=None):
        U.add_name(self.doc, key, sh_name, c1, r1, c2, r2)
        self.names[key] = (sh_name, c1, r1, c2 if c2 is not None else c1,
                           r2 if r2 is not None else r1)
        return key

    def ref(self, key):
        """A1 reference string for a registered name (used inside formulas)."""
        sh, c1, r1, c2, r2 = self.names[key]
        a = U.addr(sh, c1, r1)
        b = U.addr(sh, c2, r2)
        return a if a == b else f"{a}:{b}"

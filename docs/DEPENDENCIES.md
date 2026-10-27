# Dependency review

Reviewed October 26, 2026 (America/Phoenix).

| Component | Installed version | Source and role | License |
| --- | --- | --- | --- |
| Python | 3.12.14 | Existing bundled runtime; isolated project environment | PSF and bundled notices |
| Gmsh | 4.15.2 | [Official PyPI package](https://pypi.org/project/gmsh/); CAD/meshing | GPL-2.0-or-later |
| NumPy | 2.3.4 | [PyPI](https://pypi.org/project/numpy/2.3.4/); mesh/result arrays | BSD-3-Clause and bundled library notices |
| CalculiX | 2.23 | [Author's download page](https://www.dhondt.de/); external `ccx_static.exe` using SPOOLES | GPL; upstream program states version 2 or later; bundled libraries have separate notices |
| pytest | 8.4.2 | [PyPI](https://pypi.org/project/pytest/8.4.2/); tests only | MIT |
| setuptools | 80.9.0 | [PyPI](https://pypi.org/project/setuptools/80.9.0/); local build | MIT |
| REA | 6.8.0 | [morluto/rea](https://github.com/morluto/rea); separate optional research CLI | MIT; transitive components retain their notices |
| Matplotlib | 3.10.8 | Official PyPI package; validation plots | Matplotlib license, BSD compatible; dependencies retain notices |

`requirements-validation-win-py312.lock` adds plotting wheels and includes the core lock. The desktop lock includes that validation lock, so the full test suite and cantilever report generator are installed together. PySide6 6.10.2 and the MCP SDK 1.26.0 remain pinned in the desktop lock.

`requirements-win-py312.lock` records every installed project/test/build wheel version and SHA-256 for Windows x64 / Python 3.12. Pip's installation reports were used to capture artifact hashes. `tools/rea/package-lock.json` records REA's dependency graph and registry integrity values. Pip and the existing runtimes are bootstrap prerequisites, not included in those locks.

CalculiX archive: `https://www.dhondt.de/calculix_2.23_4win.zip`.
Observed SHA-256: `87fc4e1721df37370ec67d0a244bb14f9bf804b0a95df49e2ae7369d30ec72e8`.
This records the downloaded bytes for repeatability; it is not an independently verified publisher signature. The archive's `README_Install` identifies its binary contributor and the author's source archives. Only the static solver is invoked; other executables present in the upstream archive are unused and excluded from Git.

Original orchestration is GPL-2.0-or-later, consistent with using the GPL Gmsh API. This does not relicense dependencies. Preserve upstream license files and review the complete binary dependency notices before distributing a packaged application.

Official references:

- [Gmsh documentation and public API](https://gmsh.info/doc/texinfo/)
- [Gmsh license conditions](https://gmsh.info/doc/texinfo/#Copying-conditions)
- [CalculiX manual](https://www.dhondt.de/ccx_2.23.pdf)
- [CalculiX source archive](https://www.dhondt.de/ccx_2.23.src.tar.bz2)

The default `.gitignore` excludes `.venv`, `.tools`, Python caches and `runs`. REA is not a dependency of the simulation package. No proprietary Ansys files are required.

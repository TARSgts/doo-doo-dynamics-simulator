"""Install the pinned official native SU2 release; no administrator rights."""
import hashlib
import io
from pathlib import Path
import sys
import urllib.request
import zipfile

URL='https://github.com/su2code/SU2/releases/download/v8.5.0/SU2-v8.5.0-win64-omp.zip'
SHA256='4466fe21aedb5e0bad57afd45f829acbdec6ec79fe8c3f8954ddea06a4b4bc11'


def install(root=None):
    if sys.platform!='win32':raise RuntimeError('This installer targets Windows x64. On other systems install SU2 and set SU2_CFD_EXECUTABLE.')
    root=Path(root or Path(__file__).resolve().parents[1]/'.tools/su2/v8.5.0').resolve()
    raw=urllib.request.urlopen(URL,timeout=90).read()
    if hashlib.sha256(raw).hexdigest()!=SHA256:raise ValueError('SU2 archive checksum mismatch; nothing was installed')
    def extract(archive):
        for name in archive.namelist():
            if not (root/name).resolve().is_relative_to(root):raise ValueError('Unsafe path in SU2 archive')
        archive.extractall(root)
    outer=zipfile.ZipFile(io.BytesIO(raw))
    root.mkdir(parents=True,exist_ok=True)
    nested=outer.read('win64-omp.zip')
    extract(zipfile.ZipFile(io.BytesIO(nested)))
    # Preserve the project's license alongside the upstream release distribution.
    license_url='https://raw.githubusercontent.com/su2code/SU2/v8.5.0/COPYING'
    (root/'COPYING').write_bytes(urllib.request.urlopen(license_url,timeout=30).read())
    executable=root/'bin/SU2_CFD.exe'
    if not executable.is_file():raise FileNotFoundError('SU2 release did not contain SU2_CFD.exe')
    return executable


if __name__=='__main__':print(install())

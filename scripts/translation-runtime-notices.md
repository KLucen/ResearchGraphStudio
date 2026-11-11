# Bundled PDF translation runtime

The application distributes the unmodified official PDFMathTranslate-next 2.10.2 Windows runtime with BabelDOC 0.7.1 and offline assets. The pinned download URLs, sizes and SHA-256 digests are in `translation-runtime-manifest.json`. The preparation script verifies every download before extraction. It preserves the complete original bundle, including Python, all package metadata/licenses, the PyStand launcher and VC++ redistributable installers. It does not install dependencies or contact a model provider.

## Original licenses and source

PDFMathTranslate-next and BabelDOC include GNU AGPL version 3 license texts. Their fixed-tag complete source archives are beside this document. Preserve copyright, license, warranty and modification notices, and corresponding-source availability described in the original license sections 4–6 and 13. The runtime itself is not modified by this application; the application's adapter is separate source distributed with the application. This document does not determine license compatibility or replace the original terms.

PyMuPDF 1.28.2 metadata declares GNU AGPL v3 or Artifex Commercial License; no commercial license is assumed. Its exact PyPI source distribution and MuPDF 1.28.2 complete source distribution are included. PyMuPDF's original `setup.py` pins `version_mupdf = '1.28.2'` and documents `PYMUPDF_SETUP_MUPDF_BUILD`; its `pyproject.toml`, build scripts and `COPYING` are preserved in the source archive. MuPDF includes its `COPYING`, `Makefile`, `platform/win32`, `scripts`, and bundled `thirdparty` source and original licenses. To build, extract both archives and follow the original PyMuPDF build instructions, setting `PYMUPDF_SETUP_MUPDF_BUILD` to the extracted matching MuPDF directory. Build dependencies and compilers are developer prerequisites, not installer prerequisites.

Levenshtein 0.27.5 (GPL-2.0-or-later) and marisa-trie 1.4.1 (MIT plus the original BSD/LGPL alternative for bundled marisa) exact source distributions are included. SciPy 1.18.1's source distribution preserves its bundled third-party notices and build definitions; the official wheel's original notices remain in site-packages. These source copies do not imply byte-for-byte reproducibility of an upstream binary: the upstream wheel toolchains and full transitive build environment are not recreated here.

Python's original license is `runtime/LICENSE.txt`. PyStand 1.1.4's MIT notice is supplied in `PyStand-LICENSE.txt`. All 135 upstream Python package metadata directories and their original licenses remain intact. Do not remove dist-info directories or attribute the complete distribution to a single license.

## Offline resources

The official `offline_assets_*.zip` includes fonts, the DocLayout-YOLO ONNX model, tiktoken cache and CMaps. The original launcher restores them and BabelDOC verifies their embedded hashes. The application uses an isolated home/cache directory. Availability without external asset downloads must also be verified by an actual installed-runtime test; source inspection alone is not that test.

The original BabelDOC-Assets README lists font origins and licenses. Copies of the available original notices accompany this file: Go Noto Universal (Unlicense and its included upstream notice), Source Han TrueType, LXGW WenKai GB/TC, Klee and Noto (OFL 1.1), and MaruBuri's copyright/license statement. Model cards for the original DocLayout-YOLO model and the ONNX conversion both declare Apache-2.0 and are included. Keep these attribution files with the offline assets.

No private paper, API credential, local database or real model output is included. Download URLs are public upstream URLs; hashes prevent a changed upstream file from being silently accepted.

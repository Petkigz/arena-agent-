# Vendored OpenCV cascades

`haarcascade_frontalface_default.xml` — the classic frontal-face Haar
cascade, taken from the opencv-python 4.10 wheel (`cv2/data/`), which
carries OpenCV's Apache 2.0 license and Rainer Lienhart's copyright
notice in the file header.

Why vendored: OpenCV 5 wheels no longer bundle cascade data, so
`cv2.data.haarcascades` is an empty/absent path on modern installs and
face detection silently degrades (live 2026-09-05: "Face cascade not
found in candidates" on every diag run). The detector tries this
directory first, then `cv2.data`, then the system paths.

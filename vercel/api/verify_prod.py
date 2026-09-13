import io, urllib.request, zipfile, sys
from pathlib import Path

here = Path(__file__).resolve().parent
A = (here / "../hwpx-train-pairs/01_culture_cctv/A_style.hwpx").resolve()
B = (here / "../hwpx-train-pairs/01_culture_cctv/B_content.hwpx").resolve()
print("A:", A, A.exists(), A.stat().st_size)
print("B:", B, B.exists(), B.stat().st_size)

import transplant
c_local = here / "test_local.hwpx"
summary = transplant.run(A, B, c_local)
print("로컬 C 크기:", c_local.stat().st_size)
z = zipfile.ZipFile(c_local)
print("엔트리 수:", len(z.namelist()))
print("mimetype:", z.read("mimetype").decode())
print("testzip:", z.testzip())
for n in z.namelist():
    info = z.getinfo(n)
    print(f"  {n:30s} compress_type={info.compress_type} size={info.file_size} compressed={info.compress_size}")

vercel_url = "https://vercel-7g20wr5h3-hmm-6ffb.vercel.app/api/transplant"
print("\nVercel URL:", vercel_url)

boundary = "----TestBoundary9876543210"
header_a = ('--' + boundary + '\r\n'
            'Content-Disposition: form-data; name="style"; filename="style.hwpx"\r\n'
            'Content-Type: application/octet-stream\r\n\r\n').encode()
header_b = ('\r\n--' + boundary + '\r\n'
            'Content-Disposition: form-data; name="content"; filename="content.hwpx"\r\n'
            'Content-Type: application/octet-stream\r\n\r\n').encode()
footer = ('\r\n--' + boundary + '--\r\n').encode()
body = header_a + A.read_bytes() + header_b + B.read_bytes() + footer

req = urllib.request.Request(
    vercel_url,
    data=body,
    method='POST',
    headers={
        'Content-Type': 'multipart/form-data; boundary=' + boundary,
        'Accept': 'application/hwp+zip',
    },
)
print("요청 전송...")
with urllib.request.urlopen(req, timeout=60) as resp:
    data = resp.read()
print("HTTP:", resp.status)
print("Content-Type:", resp.headers.get("Content-Type"))
print("Content-Disposition:", resp.headers.get("Content-Disposition"))
print("받은 바이트:", len(data))
print("첫 4바이트:", data[:4])

c_prod = here / "test_v_prod.hwpx"
c_prod.write_bytes(data)
print("저장:", c_prod, c_prod.stat().st_size)

print("\n=== Vercel 결과 ZIP 검사 ===")
z2 = zipfile.ZipFile(c_prod)
print("엔트리 수:", len(z2.namelist()))
print("mimetype:", z2.read("mimetype").decode())
print("testzip:", z2.testzip())
for n in z2.namelist():
    info = z2.getinfo(n)
    print(f"  {n:30s} compress_type={info.compress_type} size={info.file_size} compressed={info.compress_size}")

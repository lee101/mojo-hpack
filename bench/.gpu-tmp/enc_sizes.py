import ctypes, os, sys, time, statistics
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "python"))
from hpack import _lib
LIB=_lib.lib(); CODES=ctypes.addressof(_lib._CODES); LENGTHS=ctypes.addressof(_lib._LENGTHS)
H=(b"content-type: application/json; charset=utf-8\r\n"
   b"cache-control: no-cache\r\n"
   b"x-request-id: 9f3f7f2bb12e4a178dc44bc71782ee9d\r\n")
def best(fn,reps,runs=7):
    for _ in range(5): fn()
    o=[]
    for _ in range(runs):
        t=float('inf')
        for _ in range(reps):
            s=time.perf_counter(); fn(); t=min(t,time.perf_counter()-s)
        o.append(t/reps)
    return min(o), statistics.median(o)
def enc(buf,n,cap):
    d=_lib._allocate_bytes(cap)
    LIB.mh_huffman_encode(_lib._bytes_address(buf),n,CODES,LENGTHS,_lib._bytes_address(d))
print(f"{'n':>9} {'enc ns/B best':>13} {'enc ns/B med':>12} {'us total':>9}")
for n,reps in [(1024,50000),(4096,20000),(8192,10000),(16384,5000),(32768,3000),
               (61440,2000),(131072,1000),(262144,500),(524288,200),(1048576,100)]:
    data=(H*(n//len(H)+1))[:n]
    e=_lib.huffman_encode(data)
    b,m=best(lambda: enc(data,n,len(e)),reps)
    print(f"{n:>9} {b/n*1e9:>13.4f} {m/n*1e9:>12.4f} {b*1e6:>9.2f}")

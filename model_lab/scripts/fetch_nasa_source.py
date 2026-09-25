"""Bounded download of the battery ZIP linked by NASA's official PCoE page."""
from __future__ import annotations
import hashlib,json,time,urllib.request,zipfile,shutil
from pathlib import Path

URL='https://phm-datasets.s3.amazonaws.com/NASA/5.+Battery+Data+Set.zip'
ROOT=Path('model_lab/data/raw/nasa_pcoe')
MAX_BYTES=2*1024**3
MIN_FREE=70*1024**3

def sha(path):
    h=hashlib.sha256()
    with path.open('rb') as f:
        while b:=f.read(1024**2):h.update(b)
    return h.hexdigest()

def main():
    ROOT.mkdir(parents=True,exist_ok=True)
    out=ROOT/'battery_data_set.zip';partial=out.with_suffix('.zip.part')
    record={'url':URL,'official_page':'https://www.nasa.gov/intelligent-systems-division/discovery-and-systems-health/pcoe/pcoe-data-set-repository/','terms':'NASA PCoE requests acknowledgement and data citation. Public redistribution rights not independently assessed.','status':'pending'}
    try:
        if not out.exists():
            if shutil.disk_usage(ROOT).free<MIN_FREE+MAX_BYTES:raise RuntimeError('disk reserve insufficient')
            req=urllib.request.Request(URL,headers={'User-Agent':'BatteryResearch/1.0'})
            start=time.monotonic();count=0
            with urllib.request.urlopen(req,timeout=45) as response:
                length=int(response.headers.get('Content-Length',0))
                if length>MAX_BYTES:raise RuntimeError('source exceeds bounded download size')
                record.update(content_length=length,etag=response.headers.get('ETag'))
                with partial.open('wb') as f:
                    while block:=response.read(1024**2):
                        count+=len(block)
                        if count>MAX_BYTES or time.monotonic()-start>420:raise RuntimeError('bounded download limit reached')
                        f.write(block)
            if length and count!=length:raise RuntimeError('truncated source')
            partial.replace(out)
        with zipfile.ZipFile(out) as z:
            listing=[{'name':i.filename,'bytes':i.file_size} for i in z.infolist()]
            if sum(i.file_size for i in z.infolist())>8*1024**3:raise RuntimeError('expansion budget exceeded')
            bad=z.testzip()
            if bad:raise RuntimeError('ZIP CRC failure: '+bad)
        record.update(status='downloaded_crc_verified',bytes=out.stat().st_size,sha256=sha(out),archive_listing=listing,official_checksum='not provided; SHA256 is local identity, not an official checksum')
    except Exception as e:record.update(status='blocked_or_partial',error=repr(e))
    (ROOT/'source_record.json').write_text(json.dumps(record,indent=2))
    print(json.dumps(record,indent=2),flush=True)
    return 0 if record['status']=='downloaded_crc_verified' else 1

if __name__=='__main__':raise SystemExit(main())

from __future__ import annotations
import argparse,json
from model_lab.modeling.v2.features import build_feature_bundle

def main():
    p=argparse.ArgumentParser(description="Build prefix-only features from V2 derived tables")
    p.add_argument("--derived",required=True);p.add_argument("--out",required=True);p.add_argument("--landmarks",type=int,default=8)
    a=p.parse_args();m=build_feature_bundle(a.derived,a.out,a.landmarks)
    print(json.dumps({"rows":len(m["rows"]),"heads":m["target_definitions"],"manifest":a.out+"/features.json"},ensure_ascii=False))
if __name__=="__main__":main()

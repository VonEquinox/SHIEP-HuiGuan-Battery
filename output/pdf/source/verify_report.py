# /// script
# requires-python = ">=3.12"
# dependencies = ["reportlab==4.4.9", "pypdf==6.10.0"]
# ///
"""Check source references, archived arithmetic, font coverage and PDF structure.

Visual review is separate and must be performed on rendered PNGs.
"""
from pathlib import Path
import hashlib,json,re,subprocess
from fractions import Fraction
from pypdf import PdfReader
import build_report as build

HERE=Path(__file__).resolve().parent
ROOT=HERE.parents[2]
PDF=HERE.parent/'HuiGuan_DEV_vs_main_20261002.pdf'
pages=json.loads((HERE/'report_content.json').read_text())
layout=json.loads((HERE/'layout_receipt.json').read_text())
reader=PdfReader(PDF)
assert len(reader.pages)==layout['page_count']==62
assert hashlib.sha256(PDF.read_bytes()).hexdigest()==layout['sha256']
texts=[page.extract_text() for page in reader.pages]
assert all(len(s)>200 and '\ufffd' not in s for s in texts)
assert not re.search(r'sk-[A-Za-z0-9]{20,}','\n'.join(texts))
assert min(p['min_body_y'] for p in layout['pages'])>=65
assert min(p['body_font_scale'] for p in layout['pages'])>=.975
build.init_fonts();font=build.pdfmetrics.getFont('Han')
missing=set()
def strings(v):
    if isinstance(v,str):yield v
    elif isinstance(v,list):
        for x in v:yield from strings(x)
    elif isinstance(v,dict):
        for x in v.values():yield from strings(x)
for page in pages:
    for value in strings(page):
        rendered=build.para(value,'formula').getPlainText()
        missing.update(ch for ch in rendered if ord(ch)>32 and ord(ch) not in font.face.charToGlyph)
assert not missing,missing

source_hashes={}
for path in layout['source_index']:
    if path.startswith('main:'):
        raw=subprocess.check_output(['git','show','c4203014:'+path[5:]],cwd=ROOT)
    else:
        assert (ROOT/path).exists(),path
        raw=subprocess.check_output(['git','show','0d9a53de:'+path],cwd=ROOT)
    source_hashes[path]=hashlib.sha256(raw).hexdigest()
assert len(source_hashes)==88

data=json.loads((HERE/'data/model_score_data.json').read_text())
ratio_checks=0
for metrics in [data['development']['HM1_improvements'],data['historical_final']['M1_improvements']]:
    for model,sources in metrics.items():
        for source,row in sources.items():
            actual=(row['baseline_mae_pp']-row['candidate_mae_pp'])/row['baseline_mae_pp']*100
            assert abs(actual-row['relative_error_reduction_pct'])<1e-10
            ratio_checks+=1
for row in data['historical_final']['XJTU_only_OOD_to_joint_MATR'].values():
    actual=(row['baseline_mae_pp']-row['candidate_mae_pp'])/row['baseline_mae_pp']*100
    assert abs(actual-row['relative_error_reduction_pct'])<1e-10
    ratio_checks+=1
assert Fraction(56,21)==Fraction(8,3)
assert 100+Fraction(1000,1)/Fraction(9,10)/2-Fraction(1000,1)/Fraction(8,10)/2==Fraction(275,9)
assert 20+Fraction(1000,1)/Fraction(9,10)/2-Fraction(1000,1)/Fraction(8,10)/2==Fraction(-445,9)
assert (Fraction(77,90)-Fraction(7,10))/Fraction(7,10)*100==Fraction(200,9)

# Export all prose, tables, formulas and source paths to a searchable companion.
md=['# 慧管电池 main → DEV 完整对比报告正文', '',
    '固定实现：main c4203014 / DEV 0d9a53de；报告日期2026-10-02。图表见同目录上级PDF。','']
for number,page in enumerate(pages,2):
    md += [f'## 第{number}页 · {page["title"]}', '',page['subtitle'],'']
    for b in page['blocks']:
        ty=b['type']
        if ty in ('p','h2','formula','callout'):
            label=('### '+b['text']) if ty=='h2' else ((b.get('label','公式与口径')+'：'+b['text']) if ty in ('formula','callout') else b['text'])
            md += [label,'']
        elif ty=='table':
            def cell(v):return str(v).replace('|','\\|').replace('\n','<br>')
            md += ['| '+' | '.join(map(cell,b['headers']))+' |','| '+' | '.join('---' for _ in b['headers'])+' |']
            md += ['| '+' | '.join(map(cell,row))+' |' for row in b['rows']]+['']
        elif ty in ('chart','diagram'):md += [f'[{ty}：{b["kind"]}，请查看PDF对应页]','']
        elif ty=='image':md += [b['caption'],'']
    md+=['来源：'+ '；'.join(page.get('sources',[])),'']
(HERE/'report_content.md').write_text('\n'.join(md).rstrip()+'\n')
receipt={
    'pdf_sha256':layout['sha256'],'pages':len(reader.pages),'source_count':len(source_hashes),
    'source_hashes':source_hashes,'source_versions':{'main':'c4203014','DEV':'0d9a53de'},'arithmetic_ratio_checks':ratio_checks,
    'font_missing_glyphs':[],'pdf_text_extraction':'all_pages_passed',
    'minimum_body_font_size_pt':10.6*min(p['body_font_scale'] for p in layout['pages']),
    'minimum_body_bottom_pt':min(p['min_body_y'] for p in layout['pages']),
    'chart_count':sum(b['type']=='chart' for p in pages for b in p['blocks']),
    'diagram_count':sum(b['type']=='diagram' for p in pages for b in p['blocks']),
    'formula_count':sum(b['type']=='formula' for p in pages for b in p['blocks']),
    'table_count':sum(b['type']=='table' for p in pages for b in p['blocks']),
    'visual_review':'see visual_review.json; not inferred from structure checks',
    'new_cloud_calls':0,'new_model_training_runs':0,'new_test_set_scoring_runs':0
}
(HERE/'qa_receipt.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2)+'\n')
print(json.dumps({k:v for k,v in receipt.items() if k!='source_hashes'},ensure_ascii=False))

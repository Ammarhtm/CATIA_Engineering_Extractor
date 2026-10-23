"""Read Pipeline 2 full_frame.png outputs and write provisional OCR reports.

Run from project root:
    python -m catia_extractor.ocr.run_from_pipeline2
Optional:
    python -m catia_extractor.ocr.run_from_pipeline2 --project-root "C:\\path\\CATIA_Engineering_Extractor"

Never modifies vision_report.json. No CATIA session is needed.
"""
from __future__ import annotations
import argparse
import json
from pathlib import Path
from .gdt_ocr import extract_gdt_image, VERSION


def _save_json(path, obj):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj,indent=2,ensure_ascii=False),encoding='utf-8')


def run(project_root=None):
    root = Path(project_root) if project_root else Path(__file__).resolve().parents[3]
    base = root / 'output' / 'pipeline_v2'
    source=base/'vision_report.json'
    if not source.is_file():
        raise FileNotFoundError(f'Missing Pipeline 2 report: {source}')
    report=json.loads(source.read_text(encoding='utf-8-sig'))
    output={'ocr_version':VERSION,'source_report':str(source),
            'engineering_approval':False,'results':[]}
    for row in report.get('results',[]):
        name=row.get('annotation_name','unknown')
        ann_id=str(row.get('annotation_id',''))
        # Same safe filename convention as runner.py.
        import re
        safe=re.sub(r'[<>:"/\\|?*\x00-\x1f]', '_', ann_id).strip(' .') or 'unnamed_annotation'
        folder=base/'annotations'/safe
        crop=folder/'full_frame.png'
        entry={'annotation_name':name,'annotation_id':ann_id,
               'full_frame_file':str(crop),'engineering_approval':False}
        if not crop.is_file():
            entry['status']='missing_full_frame'
            entry['reason']='No full_frame.png (visual localization not established)'
        else:
            try:
                data=extract_gdt_image(crop)
                entry.update(data)
                _save_json(folder/'ocr_report.json',entry)
            except Exception as exc:
                entry['status']='ocr_error'
                entry['error']=repr(exc)
        output['results'].append(entry)
        print(f"{name}: {entry['status']} | tolerance={entry.get('tolerance')} | "
              f"datum={entry.get('datum_references', [])}")
    output['frames_with_ocr_candidates']=sum(
        item.get('status')=='needs_visual_review' and item.get('tolerance') is not None
        for item in output['results']
    )
    destination=base/'ocr_report.json'
    _save_json(destination,output)
    print('OCR report:',destination)
    return output


def main():
    ap=argparse.ArgumentParser(description='Offline GD&T OCR over Pipeline 2 crops')
    ap.add_argument('--project-root',default=None)
    args=ap.parse_args()
    run(args.project_root)


if __name__=='__main__':
    main()

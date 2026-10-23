"""Non-semantic GD&T recognition from cropped CATIA feature-control frames.

Offline, advisory OCR. Nothing in this module changes CATIA or approves engineering
values. Uses Tesseract for text and user-supplied symbol templates for CAD glyphs.

API:
    extract_gdt_frame(frame_bgr, template_dir=Path(...)) -> JSON-serializable dict
    extract_gdt_image(path, template_dir=...) -> dict

Supports three-cell frames ([symbol][value+modifiers][datum]) as a first step.
More complicated/multi-row frames are marked as needing human review.
"""
from __future__ import annotations

from collections import Counter
from pathlib import Path
import re
import cv2
import numpy as np
import pytesseract

VERSION = "ocr-pilot-v1"
SYMBOLS = {"perpendicularity": "⊥", "flatness": "▱"}
MODIFIERS = {"diameter": "⌀", "mmc": "Ⓜ"}


def _neutral_strokes(img):
    """White/neutral bright strokes; exclude blue/purple CAD background."""
    b, g, r = [img[:, :, i].astype(np.int16) for i in range(3)]
    low = np.minimum(np.minimum(b, g), r)
    high = np.maximum(np.maximum(b, g), r)
    # For original screenshots bright >185 works on two sample palettes.
    return np.uint8((low >= 175) & ((high - low) <= 65)) * 255


def _foreground(img):
    """Return binary glyph mask, cropped to foreground bounds."""
    if img.ndim == 3 and img.shape[2] == 4 and np.any(img[:, :, 3] < 245):
        mask = (img[:, :, 3] > 20).astype('uint8') * 255
    else:
        mask = _neutral_strokes(img) if img.ndim == 3 else np.uint8(img > 180)*255
    pts = cv2.findNonZero(mask)
    if pts is None: return mask
    x,y,w,h = cv2.boundingRect(pts)
    return mask[y:y+h, x:x+w]


def _vertical_lines(frame):
    binary = _neutral_strokes(frame)
    h,w = binary.shape
    opening = cv2.morphologyEx(binary, cv2.MORPH_OPEN,
                   cv2.getStructuringElement(cv2.MORPH_RECT,(1, max(7,int(h*0.3)))))
    ya,yb = max(1,int(h*.18)), min(h-1,int(h*.82))
    scores = []
    for x in range(1,w-1):
        band1 = binary[ya:yb,max(0,x-1):min(w,x+2)]
        band2 = opening[ya:yb,max(0,x-1):min(w,x+2)]
        raw=float(np.mean(np.any(band1>0,axis=1)))
        line=float(np.mean(np.any(band2>0,axis=1)))
        scores.append((x, .35*raw+.65*line))
    groups=[]
    for x,score in scores:
        if score < .79: continue
        if groups and x-groups[-1][-1][0] <= 2: groups[-1].append((x,score))
        else: groups.append([(x,score)])
    return [(int(max(g,key=lambda q:q[1])[0]),round(float(max(s for _,s in g)),3)) for g in groups],binary


def _detect_cells(frame):
    h,w=frame.shape[:2]
    candidates,binary = _vertical_lines(frame)
    if len(candidates)<4:
        return None, {'reason':'not enough continuous vertical lines', 'line_candidates':candidates}
    # Get outer walls using visible uninterrupted lines and tolerate crop padding.
    outer_left=min(candidates,key=lambda q:q[0])[0]
    outer_right=max(candidates,key=lambda q:q[0])[0]
    if outer_left > int(w*.12) or outer_right < int(w*.85):
        return None, {'reason':'outer walls not identified','line_candidates':candidates}
    choices=[]
    for x1,s1 in candidates:
        for x2,s2 in candidates:
            if x2<=x1: continue
            cw1=x1-outer_left; cw2=x2-x1; cw3=outer_right-x2
            if not (.57*h<=cw1<=1.5*h and .52*h<=cw3<=1.25*h): continue
            if cw2 < .7*h: continue
            if x1<=outer_left+3 or x2>=outer_right-3:continue
            # Line density and expected approximately square symbol/datum cells.
            geometry=abs(cw1/h-.85)+abs(cw3/h-.78)
            choices.append((s1+s2-.6*geometry,x1,x2))
    if not choices:
        return None,{'reason':'no plausible 3-cell divider pair','line_candidates':candidates}
    _,sep1,sep2=max(choices)
    # Drop border strokes (2 px) from each logical cell.
    bounds=[outer_left,sep1,sep2,outer_right]
    cells=[]
    for a,b in zip(bounds,bounds[1:]):
        x0=max(a+2,0);x1=min(b-2,w)
        y0=max(1,int(h*.12));y1=min(h,int(h*.88))
        if x1<=x0: return None, {'reason':'empty cell'}
        cells.append(frame[y0:y1,x0:x1].copy())
    return cells,{'line_candidates':candidates,'outer_walls':[outer_left,outer_right],
                  'separators':[sep1,sep2],'bounds':bounds,'status':'provisional'}


def _match_mask(template_img, target_img):
    """Shape matching over a range of glyph sizes with location evidence."""
    templ=_foreground(template_img)
    target=_neutral_strokes(target_img)
    th,tw=templ.shape[:2];h,w=target.shape[:2]
    if th<4 or tw<3 or h<12 or w<9:return None
    # Character height depends on screenshot scale; use cell height only.
    minheight=max(9,int(h*.43));maxheight=max(minheight,min(h,int(h*.92)))
    best=None
    for sizeh in range(minheight,maxheight+1,2):
        sizew=max(3,int(round(tw*sizeh/th)))
        if sizew>w or sizeh>h:continue
        resized=cv2.resize(templ,(sizew,sizeh),interpolation=cv2.INTER_NEAREST)
        corr=cv2.matchTemplate(target,resized,cv2.TM_CCORR_NORMED)
        _,peak,_,loc=cv2.minMaxLoc(corr)
        x,y=loc
        patch=target[y:y+sizeh,x:x+sizew]>0
        tmask=resized>0
        dice=2*int(np.count_nonzero(patch&tmask))/max(1,int(np.count_nonzero(patch))+int(np.count_nonzero(tmask)))
        score=.45*float(peak)+.55*dice
        if best is None or score>best['score']:
            best={'score':float(score),'box':[int(x),int(y),int(sizew),int(sizeh)],
                  'dice':round(float(dice),3), 'correlation':round(float(peak),3)}
    return best


def _symbol_candidates(img,template_dir,names):
    out=[]
    for name in names:
        path=Path(template_dir)/(name+'.png')
        tpl=cv2.imread(str(path),cv2.IMREAD_UNCHANGED) if path.is_file() else None
        if tpl is None:continue
        item=_match_mask(tpl,img)
        if item is None:continue
        out.append({'name':name,'score':round(item['score'],4),
                    'box':item['box'],'dice':item['dice']})
    return sorted(out,key=lambda a:a['score'],reverse=True)


def _ocr(img,allowed='0123456789.,ABCDEFGHIJKLMNOPQRSTUVWXYZ',psms=(7,10,13)):
    # RGB-to-grayscale Otsu would keep blue/purple background; use explicit
    # neutral-stroke mask to create a black-on-white OCR image.
    mask=_neutral_strokes(img)
    variants={'binary':255-mask}
    readings=[]
    for key,source in variants.items():
        scaled=cv2.resize(source,None,fx=5,fy=5,interpolation=cv2.INTER_CUBIC)
        scaled=cv2.copyMakeBorder(scaled,18,18,18,18,cv2.BORDER_CONSTANT,value=255)
        for psm in psms:
            try:
                text=pytesseract.image_to_string(scaled,config=(
                    f'--oem 3 --psm {psm} -c tessedit_char_whitelist={allowed}')).strip().replace('\n',' ')
            except pytesseract.TesseractNotFoundError as exc:
                raise RuntimeError('Tesseract not installed or not on PATH') from exc
            if text:readings.append({'variant':key,'psm':psm,'text':text})
    return readings


def _best_datum(readings):
    values=[r['text'].strip().upper() for r in readings]
    single=[v for v in values if re.fullmatch(r'[A-Z]',v)]
    if not single:return None
    return Counter(single).most_common(1)[0][0]


def _best_number(readings):
    numbers=[]
    for record in readings:
        t=record['text'].replace(',','.').replace(' ','')
        # Only exact tokens: never silently turn OCR garbage into numbers.
        if re.fullmatch(r'\d+(?:\.\d+)?',t):numbers.append(t)
    if not numbers: return None,None
    token,count=Counter(numbers).most_common(1)[0]
    return token,float(token)


def _cut_out(img,box,pad=2):
    result=img.copy();h,w=result.shape[:2]
    x,y,bw,bh=box
    x0=max(0,x-pad);y0=max(0,y-pad)
    x1=min(w,x+bw+pad);y1=min(h,y+bh+pad)
    # Replace with inferred local background from leftmost corner of cell.
    background=np.median(np.concatenate((result[:min(3,h),:,:].reshape(-1,3),result[-min(3,h):,:,:].reshape(-1,3))),axis=0)
    result[y0:y1,x0:x1]=background.astype('uint8')
    return result


def extract_gdt_frame(frame_bgr, template_dir=None):
    """Extract conservative candidate JSON. All values pending visual validation."""
    if template_dir is None:
        template_dir = Path(__file__).resolve().parent / 'templates'
    if frame_bgr is None or frame_bgr.ndim!=3 or frame_bgr.shape[2]!=3:
        raise ValueError('Expected BGR image (cv2.imread).')
    cells,seg=_detect_cells(frame_bgr)
    base={'version':VERSION,'status':'needs_visual_review','engineering_approval':False,
          'frame_size':[int(frame_bgr.shape[1]),int(frame_bgr.shape[0])],
          'segmentation':seg,'geometric_symbol':None,'tolerance':None,
          'diameter_modifier':None,'material_condition_modifier':None,
          'datum_references':[], 'raw_ocr':{},'symbol_candidates':{},
          'warnings':[]}
    if cells is None:
        base['status']='segmentation_failed';return base
    symbol,value,datum=cells
    # Symbol glyph: not interpreted by Tesseract's alphanumeric language model.
    matches=_symbol_candidates(symbol,template_dir,SYMBOLS.keys())
    base['symbol_candidates']['geometric']=matches
    if matches and matches[0]['score']>=.68 and (len(matches)==1 or matches[0]['score']-matches[1]['score']>=.055):
        base['geometric_symbol']={'name':matches[0]['name'],
                                  'glyph':SYMBOLS[matches[0]['name']],
                                  'match_score':matches[0]['score']}
    else:base['warnings'].append('Geometric symbol ambiguous or unsupported')
    # MMC (circle-M) and diameter are independent possible modifiers.
    mmc_matches=_symbol_candidates(value,template_dir,['mmc'])
    dia_matches=_symbol_candidates(value,template_dir,['diameter'])
    base['symbol_candidates']['mmc']=mmc_matches
    base['symbol_candidates']['diameter']=dia_matches
    filtered=value.copy()
    for name,matches,threshold,location in (
        ('mmc',mmc_matches,.62,'right'),('diameter',dia_matches,.64,'left')):
        if not matches:continue
        match=matches[0];cx=(match['box'][0]+match['box'][2]*.5)/max(1,value.shape[1])
        plausible=(cx>.53 if location=='right' else cx<.40)
        if match['score']>=threshold and plausible:
            if name=='mmc':base['material_condition_modifier']='MMC'
            else:base['diameter_modifier']='⌀'
            filtered=_cut_out(filtered,match['box'],pad=1)
    # Additional geometry evidence for a circled-M glyph. In small CATIA
    # screenshots Tesseract often returns '0' or 'M' for this symbol.
    # Only use this fallback if a circular glyph in the right half is present
    # AND the loose MMC template also supports it (never OCR text alone).
    if base['material_condition_modifier'] is None and mmc_matches:
        hh,ww=value.shape[:2]
        gray=cv2.cvtColor(value,cv2.COLOR_BGR2GRAY)
        circles=cv2.HoughCircles(gray,cv2.HOUGH_GRADIENT,dp=1.0,
                 minDist=max(10,int(hh*.3)),param1=100,param2=16,
                 minRadius=max(6,int(hh*.29)),maxRadius=max(9,int(hh*.51)))
        circles_list=[] if circles is None else circles[0].tolist()
        supported=[(cx,cy,r) for cx,cy,r in circles_list
                   if cx > ww*.55 and mmc_matches[0]['score']>=.44]
        if supported:
            cx,cy,r=max(supported,key=lambda c:c[2]);
            base['material_condition_modifier']='MMC'
            x0=max(0,int(cx-r-2));y0=max(0,int(cy-r-2))
            x1=min(ww,int(cx+r+3));y1=min(hh,int(cy+r+3))
            filtered=_cut_out(filtered,[x0,y0,x1-x0,y1-y0],pad=0)
            base['symbol_candidates']['mmc_circle_evidence']={
                'center':[round(cx,1),round(cy,1)], 'radius':round(r,1),
                'support':'hough_circle_and_mmc_template'}

    raw = _ocr(filtered,allowed='0123456789.,',psms=(6,7,10,13))
    # Keep raw unfiltered for comparison, but never use it as value if it
    # contains non-numeric tokens.
    base['raw_ocr']['value_filtered']=raw
    base['raw_ocr']['value_unfiltered']=_ocr(value,psms=(7,10))
    token,num=_best_number(raw)
    # Symbol-aware OCR: in a frame such as [⊥][⌀0Ⓜ][A], the OCR often
    # mistakes the circled M for a zero. Isolate the numeric span using
    # matching positions, *not* by assuming any particular tolerance value.
    if (base['diameter_modifier'] is not None or
            base['material_condition_modifier'] is not None):
        low=2;high=value.shape[1]-2
        if base['diameter_modifier'] is not None and dia_matches:
            xx,yy,ww,hh=dia_matches[0]['box']
            low=max(low,xx+ww+2)
        if base['material_condition_modifier'] is not None and mmc_matches:
            xx,yy,ww,hh=mmc_matches[0]['box']
            high=min(high,xx-2)
        if high-low>=9:
            numeric_roi=value[3:-3,low:high]
            roi_reads=_ocr(numeric_roi,allowed='0123456789.,',psms=(6,7,10,13))
            base['raw_ocr']['numeric_roi']=roi_reads
            roi_token,roi_num=_best_number(roi_reads)
            if roi_token is not None:
                token,num=roi_token,roi_num
                base['raw_ocr']['numeric_roi_source']='between_detected_modifiers'
    if token is not None:base['tolerance']={'raw':token,'value':num}
    else:base['warnings'].append('Tolerance number not reliably read; review value cell')
    datum_readings=_ocr(datum,allowed='ABCDEFGHIJKLMNOPQRSTUVWXYZ',psms=(6,7,10,13))
    base['raw_ocr']['datum']=datum_readings
    d=_best_datum(datum_readings)
    if d:base['datum_references']=[d]
    else:base['warnings'].append('Datum not reliably read')
    base['segmentation']['cell_sizes']=[[int(c.shape[1]),int(c.shape[0])] for c in cells]
    return base


def extract_gdt_image(path,template_dir=None):
    img=cv2.imread(str(path))
    if img is None: raise FileNotFoundError(f'Cannot read image: {path}')
    data=extract_gdt_frame(img,template_dir)
    data['source_image']=str(path)
    return data

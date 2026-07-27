"""Build the blind v10 dynamic-enhancement ROI review gallery."""
import argparse,json
from pathlib import Path
from dtwin.benchmark.openswisshcc_localizer_enhancement_roi import build_enhancement_roi_pilot
def main():
 p=argparse.ArgumentParser();p.add_argument('--localizer-run',type=Path,required=True);p.add_argument('--manifest',type=Path,required=True);p.add_argument('--inputs-root',type=Path,required=True);p.add_argument('--registration-root',type=Path,required=True);p.add_argument('--out',type=Path,required=True);p.add_argument('--max-components',type=int,default=3);p.add_argument('--roi-mm',type=float,default=80);a=p.parse_args();r=build_enhancement_roi_pilot(localizer_run=a.localizer_run,input_manifest=a.manifest,input_root=a.inputs_root,registration_root=a.registration_root,output_root=a.out,max_components=a.max_components,roi_mm=a.roi_mm);print(json.dumps({"case_count":r["case_count"],"panel_count":r["panel_count"],"gallery_signature":r["gallery_signature"]}));return 0
if __name__=='__main__':raise SystemExit(main())


import { describe,expect,it } from 'vitest';
import { placeDiagnosticsPopup } from './diagnosticsPosition';

describe('anchored Status pop-up positioning',()=>{
  it('places a desktop pop-up under the indicator without leaving the viewport',()=>{
    const pos=placeDiagnosticsPopup(
      {left:1000,right:1090,top:18,bottom:58},{height:480},
      {width:1280,height:800});
    expect(pos).toEqual({side:'below',left:630,top:66,width:460,maxHeight:722});
  });
  it('clamps horizontally when the indicator is near the viewport left edge',()=>{
    const pos=placeDiagnosticsPopup(
      {left:20,right:75,top:10,bottom:55},{height:350},
      {width:700,height:650});
    expect(pos.left).toBe(12);
    expect(pos.left+pos.width).toBeLessThanOrEqual(688);
  });
  it('uses a viewport-safe width on a narrow mobile device',()=>{
    const pos=placeDiagnosticsPopup(
      {left:238,right:292,top:12,bottom:54},{height:590},
      {width:320,height:640});
    expect(pos.width).toBe(296);
    expect(pos.left).toBe(12);
    expect(pos.top).toBe(62);
    expect(pos.maxHeight).toBeLessThanOrEqual(640-pos.top-12);
  });
  it('flips above a lower-page trigger when there is more usable space',()=>{
    const pos=placeDiagnosticsPopup(
      {left:390,right:470,top:610,bottom:650},{height:410},
      {width:720,height:700});
    expect(pos.side).toBe('above');
    expect(pos.top).toBe(192);
    expect(pos.maxHeight).toBe(590);
  });
  it('keeps a tall panel bounded in a short viewport',()=>{
    const pos=placeDiagnosticsPopup(
      {left:200,right:260,top:20,bottom:56},{height:1200},
      {width:480,height:280});
    expect(pos.top).toBe(64);
    expect(pos.maxHeight).toBe(204);
    expect(pos.left+pos.width).toBeLessThanOrEqual(480-12);
  });
});

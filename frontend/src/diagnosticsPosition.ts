/** Place the status panel beside its trigger without spilling outside the viewport.
 *
 * Portal positioning is independent of the sticky header and navigation
 * stacking contexts. A short viewport favors the side with more space and
 * makes the panel itself scrollable rather than moving the page.
 */
export type Rect = {left:number;right:number;top:number;bottom:number};
export type PopupPlacement = {
  left:number;top:number;width:number;maxHeight:number;side:'above'|'below';
};

export function placeDiagnosticsPopup(
  anchor:Rect, panel:{height:number}, viewport:{width:number;height:number},
): PopupPlacement {
  const edge=12;
  const gap=8;
  const width=Math.max(0,Math.min(460,viewport.width-2*edge));
  const left=Math.max(edge,Math.min(anchor.right-width,viewport.width-edge-width));
  const below=Math.max(0,viewport.height-anchor.bottom-gap-edge);
  const above=Math.max(0,anchor.top-gap-edge);
  const side: 'above'|'below' =
    below < Math.min(panel.height,340) && above > below ? 'above' : 'below';
  const maxHeight=Math.max(0,Math.floor(side==='above'?above:below));
  const top=side==='above'
    ? Math.max(edge,anchor.top-gap-Math.min(panel.height,maxHeight))
    : Math.min(anchor.bottom+gap,viewport.height-edge);
  return {left:Math.round(left),top:Math.round(top),width:Math.round(width),
    maxHeight,side};
}

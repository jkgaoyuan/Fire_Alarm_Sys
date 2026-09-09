/**
 * 电子地图坐标换算（F-14 / FR-015）
 *
 * 设备存的是 `map_x/map_y`——平面图**原图像素坐标**，Y 轴向下（`map_origin='top_left'`）；
 * Leaflet `CRS.Simple` 的图像叠加把 bounds 左下当作原点，Y 轴向上。
 * 两套 Y 方向相反，所有换算都必须经过这里，视图层不再各自翻转。
 */

export function clamp(value, min, max) {
  if (Number.isNaN(value)) return min
  return Math.min(Math.max(value, min), max)
}

/** 像素 → 相对平面图的归一化坐标（0~1），供百分比定位与点位拖拽回写 */
export function pixelToRatio(x, y, width, height) {
  if (!width || !height) return { nx: 0, ny: 0 }
  return { nx: clamp(x / width, 0, 1), ny: clamp(y / height, 0, 1) }
}

export function ratioToPixel(nx, ny, width, height) {
  return { x: nx * width, y: ny * height }
}

/**
 * 基准变更换算：平面图上传时会被等比压缩（>2000px → 2000px），
 * 早先按原图标注的点位必须按新基准缩放，否则压缩后点位会整体偏移。
 */
export function rescalePixels(x, y, fromWidth, fromHeight, toWidth, toHeight) {
  if (!fromWidth || !fromHeight || !toWidth || !toHeight) return { x, y }
  return {
    x: (x / fromWidth) * toWidth,
    y: (y / fromHeight) * toHeight,
  }
}

/** 图像叠加范围：CRS.Simple 下 [纬度范围, 经度范围]，单位为像素 */
export function imageBounds(width, height) {
  return [
    [0, 0],
    [height, width],
  ]
}

function flipsY(origin) {
  return (origin || 'top_left') === 'top_left'
}

export function pixelToLatLng(x, y, width, height, origin = 'top_left') {
  return [flipsY(origin) ? height - y : y, x]
}

export function latLngToPixel(latlng, width, height, origin = 'top_left') {
  const [lat, lng] = Array.isArray(latlng) ? latlng : [latlng.lat, latlng.lng]
  return { x: lng, y: flipsY(origin) ? height - lat : lat }
}

/**
 * 视口 → 后端 bbox 参数（`xmin,ymin,xmax,ymax`，原图像素）。
 * 视口可能拖到图外，越界部分裁剪到图像范围，避免整段查询落空。
 */
export function boundsToBbox(bounds, width, height, origin = 'top_left') {
  if (!bounds) return null
  const nw = bounds.getNorthWest ? bounds.getNorthWest() : bounds.nw
  const se = bounds.getSouthEast ? bounds.getSouthEast() : bounds.se
  const p1 = latLngToPixel(nw, width, height, origin)
  const p2 = latLngToPixel(se, width, height, origin)
  return {
    xmin: clamp(Math.min(p1.x, p2.x), 0, width),
    xmax: clamp(Math.max(p1.x, p2.x), 0, width),
    ymin: clamp(Math.min(p1.y, p2.y), 0, height),
    ymax: clamp(Math.max(p1.y, p2.y), 0, height),
  }
}

export function formatBbox(bbox) {
  if (!bbox) return ''
  const round = (value) => Math.round(value * 100) / 100
  return [round(bbox.xmin), round(bbox.ymin), round(bbox.xmax), round(bbox.ymax)].join(',')
}

/** 视口换算一步到位：Leaflet bounds → 后端 bbox 查询串 */
export function bboxQuery(bounds, width, height, origin = 'top_left') {
  return formatBbox(boundsToBbox(bounds, width, height, origin))
}

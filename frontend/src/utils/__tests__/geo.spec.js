import { describe, expect, it } from 'vitest'
import {
  bboxQuery,
  boundsToBbox,
  clamp,
  imageBounds,
  latLngToPixel,
  pixelToLatLng,
  pixelToRatio,
  ratioToPixel,
  rescalePixels,
} from '../geo'

// 上传时 3000px 原图被压缩为 2000px 存储（计划 5.4），基准随之改变
const ORIGINAL = { width: 3000, height: 1500 }
const STORED = { width: 2000, height: 1000 }

function fakeBounds(northWest, southEast) {
  return {
    getNorthWest: () => northWest,
    getSouthEast: () => southEast,
  }
}

describe('geo 坐标换算', () => {
  it('像素 ↔ 归一化 ↔ Leaflet 经纬度可往返，Y 轴按 top_left 翻转', () => {
    expect(imageBounds(2000, 1000)).toEqual([
      [0, 0],
      [1000, 2000],
    ])

    const ratio = pixelToRatio(500, 250, 2000, 1000)
    expect(ratio).toEqual({ nx: 0.25, ny: 0.25 })
    expect(ratioToPixel(ratio.nx, ratio.ny, 2000, 1000)).toEqual({ x: 500, y: 250 })

    // 图像左上角在 CRS.Simple 下是最高纬度
    expect(pixelToLatLng(0, 0, 2000, 1000)).toEqual([1000, 0])
    expect(pixelToLatLng(500, 250, 2000, 1000)).toEqual([750, 500])
    expect(latLngToPixel([750, 500], 2000, 1000)).toEqual({ x: 500, y: 250 })
    expect(latLngToPixel(pixelToLatLng(120, 340, 2000, 1000), 2000, 1000)).toEqual({ x: 120, y: 340 })

    // map_origin='bottom_left' 时不做翻转
    expect(pixelToLatLng(500, 250, 2000, 1000, 'bottom_left')).toEqual([250, 500])

    // 越界点位钳制在图内，避免归一化值把标记甩出容器
    expect(pixelToRatio(9999, -500, 2000, 1000)).toEqual({ nx: 1, ny: 0 })
    expect(clamp(NaN, 0, 10)).toBe(0)
  })

  it('压缩基准变更后的点位换算与视口 bbox 序列化', () => {
    // 按 3000px 原图标注的点位，映射到 2000px 存储图上
    expect(rescalePixels(1500, 750, ORIGINAL.width, ORIGINAL.height, STORED.width, STORED.height)).toEqual({
      x: 1000,
      y: 500,
    })
    expect(rescalePixels(10, 20, 0, 0, 2000, 1000)).toEqual({ x: 10, y: 20 })

    const bounds = fakeBounds([900, 200], [400, 900])
    expect(boundsToBbox(bounds, 2000, 1000)).toEqual({ xmin: 200, ymin: 100, xmax: 900, ymax: 600 })

    // 拖到图外时裁剪到图像范围，否则后端 bbox 查询会整段落空
    const outside = fakeBounds([1800, -300], [-500, 2600])
    expect(bboxQuery(outside, 2000, 1000)).toBe('0,0,2000,1000')
    expect(bboxQuery(null, 2000, 1000)).toBe('')
    expect(bboxQuery(fakeBounds([733.336, 120.444], [311.284, 899.998]), 2000, 1000)).toBe(
      '120.44,266.66,900,688.72'
    )
  })
})

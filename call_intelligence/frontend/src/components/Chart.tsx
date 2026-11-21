import { useEffect, useRef } from 'react'
import * as echarts from 'echarts/core'
import { BarChart, LineChart, PieChart, HeatmapChart, SankeyChart } from 'echarts/charts'
import { GridComponent, TooltipComponent, LegendComponent, VisualMapComponent, DataZoomComponent, MarkLineComponent } from 'echarts/components'
import { SVGRenderer } from 'echarts/renderers'
import { cssVar, useTheme } from '@/lib/theme'

echarts.use([BarChart, LineChart, PieChart, HeatmapChart, SankeyChart, GridComponent, TooltipComponent, LegendComponent,
  VisualMapComponent, DataZoomComponent, MarkLineComponent, SVGRenderer])

// guideline series order: blue, violet, red, orange, green (then cyan, neutral)
export const palette = () => ['--chart-1', '--chart-2', '--chart-3', '--chart-4', '--chart-5', '--cyan-text', '--neutral-accent'].map(cssVar)

/** ECharts with the app's colours, redrawn on theme change and resize. `option` receives the theme colours. */
export function Chart({ option, height = 260, onClick }: {
  option: (t: { ink: string; muted: string; faint: string; line: string; panel: string; colors: string[] }) => any
  height?: number; onClick?: (p: any) => void
}) {
  const el = useRef<HTMLDivElement>(null)
  const chart = useRef<echarts.ECharts | null>(null)
  const theme = useTheme()
  useEffect(() => {
    if (!el.current) return
    chart.current = echarts.init(el.current, undefined, { renderer: 'svg' })
    const ro = new ResizeObserver(() => chart.current?.resize())
    ro.observe(el.current)
    return () => { ro.disconnect(); chart.current?.dispose() }
  }, [])
  useEffect(() => {
    const c = chart.current
    if (!c) return
    const t = { ink: cssVar('--text-primary'), muted: cssVar('--text-secondary'), faint: cssVar('--text-tertiary'), line: cssVar('--border-light'), panel: cssVar('--bg-primary'), colors: palette() }
    const o = option(t)
    c.setOption({
      color: t.colors, textStyle: { fontFamily: 'Inter, "Noto Sans Arabic", sans-serif', color: t.muted },
      tooltip: { trigger: 'axis', backgroundColor: t.panel, borderColor: t.line, textStyle: { color: t.ink }, confine: true, ...o.tooltip },
      animationDuration: 700, animationEasing: 'cubicOut', ...o,
    }, true)
    c.off('click')
    if (onClick) c.on('click', onClick)
  })
  useEffect(() => { chart.current?.resize() }, [theme])
  return <div ref={el} style={{ height, width: '100%' }} />
}

/** Guidelines: dashed grid in border-light, axis labels in tertiary text at 12 px. */
export const axis = (t: { muted: string; line: string; faint?: string }) => ({
  axisLine: { lineStyle: { color: t.line } }, axisTick: { show: false }, axisLabel: { color: t.faint ?? t.muted, fontSize: 12 },
  splitLine: { lineStyle: { color: t.line, type: 'dashed' } },
})

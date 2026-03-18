"use client";

import React, { useEffect, useRef } from 'react';
import { createChart, ColorType, IChartApi, LineSeries } from 'lightweight-charts';

interface ChartData {
    time: string;
    value: number;
}

interface SeriesData {
    name: string;
    data: ChartData[];
    color: string;
}

interface Props {
    series: SeriesData[];
}

export default function PerformanceChart({ series }: Props) {
    const chartContainerRef = useRef<HTMLDivElement>(null);
    const chartRef = useRef<IChartApi | null>(null);

    useEffect(() => {
        if (!chartContainerRef.current) return;

        const chart = createChart(chartContainerRef.current, {
            layout: {
                background: { type: ColorType.Solid, color: 'transparent' },
                textColor: '#DDD',
            },
            width: chartContainerRef.current.clientWidth,
            height: 400,
            grid: {
                vertLines: { color: 'rgba(197, 203, 206, 0.1)' },
                horzLines: { color: 'rgba(197, 203, 206, 0.1)' },
            },
            rightPriceScale: {
                borderColor: 'rgba(197, 203, 206, 0.2)',
                mode: 2, // Percentage mode
            },
            timeScale: {
                borderColor: 'rgba(197, 203, 206, 0.2)',
            },
        });

        chartRef.current = chart;

        // 使用 v5 API: addSeries(LineSeries, options)
        series.forEach((s) => {
            const lineSeries = chart.addSeries(LineSeries, {
                color: s.color,
                lineWidth: 2,
                title: s.name,
                priceScaleId: 'right',
            });

            lineSeries.setData(s.data);
        });

        // Percentage Mode
        chart.priceScale('right').applyOptions({
            mode: 2,
        });

        const handleResize = () => {
            if (chartContainerRef.current) {
                chart.applyOptions({ width: chartContainerRef.current.clientWidth });
            }
        };

        window.addEventListener('resize', handleResize);

        return () => {
            window.removeEventListener('resize', handleResize);
            chart.remove();
        };
    }, [series]);

    return (
        <div ref={chartContainerRef} className="w-full h-[400px]" />
    );
}

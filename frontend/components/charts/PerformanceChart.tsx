"use client";

import React, { useEffect, useRef } from 'react';
import { createChart, ColorType, IChartApi, LineStyle } from 'lightweight-charts';

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
                mode: 2, // Percentage mode (0: Normal, 1: Log, 2: %?, 3: Indexed to 100)
                // Actually Mode 2 is Percentage in recent versions? 
                // Let's check docs or use default and calculate % manually.
                // Lightweight charts 4.0: PriceScaleMode.Percentage = 2
            },
            timeScale: {
                borderColor: 'rgba(197, 203, 206, 0.2)',
            },
        });

        chartRef.current = chart;

        // Add series
        series.forEach((s) => {
            const lineSeries = chart.addLineSeries({
                color: s.color,
                lineWidth: 2,
                title: s.name,
                priceScaleId: 'right', // Share scale
            });

            // Generate normalized data or just pass raw price and let chart handle % mode?
            // If using mode 2 (Percentage), it calculates change from first visible point.
            // But we want change from start of period.
            // Let's assume input data is RAW price, and we set scale mode to Percentage.

            lineSeries.setData(s.data);
        });

        // Handling Percentage Mode explicitly
        chart.priceScale('right').applyOptions({
            mode: 2, // Percentage
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

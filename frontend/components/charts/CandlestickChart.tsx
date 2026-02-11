"use client";

import React, { useEffect, useRef } from 'react';
import { createChart, ColorType, IChartApi, CandlestickSeries, HistogramSeries } from 'lightweight-charts';

interface ChartData {
    time: string; // YYYY-MM-DD
    open: number;
    high: number;
    low: number;
    close: number;
    volume?: number;
}

interface Props {
    data: ChartData[];
    colors?: {
        backgroundColor?: string;
        textColor?: string;
    };
}

export default function CandlestickChart({ data, colors = {} }: Props) {
    const chartContainerRef = useRef<HTMLDivElement>(null);
    const chartRef = useRef<IChartApi | null>(null);

    const {
        backgroundColor = 'transparent',
        textColor = '#DDD',
    } = colors;

    useEffect(() => {
        if (!chartContainerRef.current) return;

        // 建立圖表
        const chart = createChart(chartContainerRef.current, {
            layout: {
                background: { type: ColorType.Solid, color: backgroundColor },
                textColor,
            },
            width: chartContainerRef.current.clientWidth,
            height: 400,
            grid: {
                vertLines: { color: 'rgba(197, 203, 206, 0.1)' },
                horzLines: { color: 'rgba(197, 203, 206, 0.1)' },
            },
            timeScale: {
                borderColor: 'rgba(197, 203, 206, 0.2)',
                timeVisible: true,
            },
            rightPriceScale: {
                borderColor: 'rgba(197, 203, 206, 0.2)',
            },
        });

        chartRef.current = chart;

        // K線圖系列 — lightweight-charts v5 API
        const candlestickSeries = chart.addSeries(CandlestickSeries, {
            upColor: '#ef5350',     // 台股慣例：紅漲
            downColor: '#26a69a',   // 綠跌
            borderVisible: false,
            wickUpColor: '#ef5350',
            wickDownColor: '#26a69a',
        });

        // 處理資料格式：排序 + 去除重複日期
        const validData = data.map(d => ({
            time: d.time,
            open: d.open,
            high: d.high,
            low: d.low,
            close: d.close,
        })).sort((a, b) => (new Date(a.time).getTime() - new Date(b.time).getTime()));

        const uniqueData: typeof validData = [];
        const seenDates = new Set<string>();
        for (const d of validData) {
            if (!seenDates.has(d.time)) {
                seenDates.add(d.time);
                uniqueData.push(d);
            }
        }

        candlestickSeries.setData(uniqueData);

        // 成交量 (Histogram) — v5 API
        const volumeSeries = chart.addSeries(HistogramSeries, {
            priceFormat: {
                type: 'volume',
            },
            priceScaleId: '', // overlay
        });

        volumeSeries.priceScale().applyOptions({
            scaleMargins: {
                top: 0.8,
                bottom: 0,
            },
        });

        const volumeData = data
            .filter(d => d.volume !== undefined)
            .map(d => ({
                time: d.time,
                value: d.volume!,
                color: d.close >= d.open ? '#ef5350' : '#26a69a',
            }))
            .sort((a, b) => (new Date(a.time).getTime() - new Date(b.time).getTime()));

        const uniqueVolume: typeof volumeData = [];
        const seenVolDates = new Set<string>();
        for (const d of volumeData) {
            if (!seenVolDates.has(d.time)) {
                seenVolDates.add(d.time);
                uniqueVolume.push(d);
            }
        }

        volumeSeries.setData(uniqueVolume);

        // Resize observer
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
    }, [data, backgroundColor, textColor]);

    return (
        <div ref={chartContainerRef} className="w-full h-[400px]" />
    );
}

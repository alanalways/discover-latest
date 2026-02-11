"use client";

import React, { useEffect, useRef } from 'react';
import { createChart, ColorType, IChartApi, ISeriesApi, UTCTimestamp } from 'lightweight-charts';

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
        lineColor?: string;
        textColor?: string;
        areaTopColor?: string;
        areaBottomColor?: string;
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

        // K線圖系列
        const candlestickSeries = chart.addCandlestickSeries({
            upColor: '#ef5350',      // 紅K (跌) - 台股慣例其實是綠跌紅漲，但這裡先照國際慣例或之後改
            downColor: '#26a69a',    // 綠K (漲)
            borderVisible: false,
            wickUpColor: '#ef5350',
            wickDownColor: '#26a69a',
        });

        // 台股慣例：紅漲綠跌
        candlestickSeries.applyOptions({
            upColor: '#ef5350',     // 紅
            downColor: '#26a69a',   // 綠
            wickUpColor: '#ef5350',
            wickDownColor: '#26a69a',
        });
        // 等等，國際是 綠漲(up) 紅跌(down)。台股是 紅漲 綠跌。
        // Lightweight chart: upColor is for "close > open".
        // So for TW, upColor should be Red (#ef5350), downColor Green (#26a69a).
        // Let's force it.
        candlestickSeries.applyOptions({
            upColor: '#ef5350',
            downColor: '#26a69a',
            wickUpColor: '#ef5350',
            wickDownColor: '#26a69a',
        });

        // 處理資料格式
        // 確保 data 已經排序且無重複
        const validData = data.map(d => ({
            time: d.time,
            open: d.open,
            high: d.high,
            low: d.low,
            close: d.close,
        })).sort((a, b) => (new Date(a.time).getTime() - new Date(b.time).getTime()));

        // 去除重複日期
        const uniqueData = [];
        const seenDates = new Set();
        for (const d of validData) {
            if (!seenDates.has(d.time)) {
                uniqueData.append(d) // JS logic error, use push
                seenDates.add(d.time);
                uniqueData.push(d);
            }
        }

        candlestickSeries.setData(uniqueData);

        // 成交量 (Histogram)
        const volumeSeries = chart.addHistogramSeries({
            priceFormat: {
                type: 'volume',
            },
            priceScaleId: '', // Set as an overlay
        });

        volumeSeries.priceScale().applyOptions({
            scaleMargins: {
                top: 0.8, // volume takes bottom 20%
                bottom: 0,
            },
        });

        const volumeData = data
            .filter(d => d.volume !== undefined)
            .map(d => ({
                time: d.time,
                value: d.volume!,
                color: d.close >= d.open ? '#ef5350' : '#26a69a', // 紅漲綠跌 matching candle
            }))
            .sort((a, b) => (new Date(a.time).getTime() - new Date(b.time).getTime()));

        // Unique volume
        const uniqueVolume = [];
        const seenVolDates = new Set();
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

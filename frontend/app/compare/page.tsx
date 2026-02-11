"use client";

import React, { useState } from 'react';
import PerformanceChart from '@/components/charts/PerformanceChart';

export default function ComparePage() {
    return (
        <div className="p-6 text-white min-h-screen bg-gray-950">
            <h1 className="text-3xl font-black mb-6">股票對比分析</h1>
            <div className="bg-gray-900 rounded-2xl p-6 border border-gray-800">
                <p className="text-gray-400">正在優化對比功能中...</p>
                {/* 之後整合多股走勢比較 */}
            </div>
        </div>
    );
}

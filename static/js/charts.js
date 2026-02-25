/**
 * =========================================
 * FARMERMAN SYSTEMS - MARKET ANALYTICS ENGINE
 * =========================================
 * Handles dynamic Chart.js rendering with 
 * predictive AI visualization.
 */

document.addEventListener("DOMContentLoaded", function() {
    'use strict';

    const chartCanvas = document.getElementById('trendChart');
    if (!chartCanvas) return;

    // 1. Brand Palette Access
    const BRAND = {
        plantGreen: '#2E7D32',
        skyBlue: '#0288D1',
        soilBrown: '#5D4037',
        gridColor: 'rgba(0, 0, 0, 0.05)'
    };

    // 2. Data Preparation with Fallbacks
    const labels = (window.farmermanData && window.farmermanData.labels) 
        ? window.farmermanData.labels 
        : ['Week 1', 'Week 2', 'Week 3', 'Week 4', 'Next Week (AI)'];
        
    const prices = (window.farmermanData && window.farmermanData.prices) 
        ? window.farmermanData.prices 
        : [2900, 3050, 3150, 3200, 3350];

    const ctx = chartCanvas.getContext('2d');

    // 3. Create a Gradient for the Fill
    const fillGradient = ctx.createLinearGradient(0, 0, 0, 400);
    fillGradient.addColorStop(0, 'rgba(46, 125, 50, 0.2)');
    fillGradient.addColorStop(1, 'rgba(46, 125, 50, 0)');

    // 4. Advanced Chart Configuration
    const config = {
        type: 'line',
        data: {
            labels: labels,
            datasets: [{
                label: 'Price in KES',
                data: prices,
                borderColor: BRAND.plantGreen,
                backgroundColor: fillGradient,
                borderWidth: 3,
                fill: true,
                tension: 0.4,
                pointRadius: 6,
                pointHoverRadius: 8,
                pointBackgroundColor: '#FFF',
                pointBorderWidth: 2,
                // Logic: Last segment of the line uses Sky Blue to denote AI Forecast
                segment: {
                    borderColor: (ctx) => {
                        return ctx.p1DataIndex === prices.length - 1 ? BRAND.skyBlue : BRAND.plantGreen;
                    },
                    borderDash: (ctx) => {
                        return ctx.p1DataIndex === prices.length - 1 ? [6, 6] : [];
                    }
                }
            }]
        },
        options: {
            responsive: true,
            maintainAspectRatio: false,
            interaction: {
                mode: 'index',
                intersect: false,
            },
            plugins: {
                legend: {
                    display: true,
                    labels: {
                        usePointStyle: true,
                        font: { family: "'Inter', sans-serif", size: 12, weight: '600' }
                    }
                },
                tooltip: {
                    backgroundColor: BRAND.soilBrown,
                    titleFont: { size: 14, weight: 'bold' },
                    padding: 12,
                    cornerRadius: 8,
                    callbacks: {
                        label: function(context) {
                            let label = context.dataset.label || '';
                            if (label) label += ': ';
                            if (context.parsed.y !== null) {
                                label += new Intl.NumberFormat('en-KE', { 
                                    style: 'currency', 
                                    currency: 'KES' 
                                }).format(context.parsed.y);
                            }
                            return context.dataIndex === prices.length - 1 ? `[AI FORECAST] ${label}` : label;
                        }
                    }
                }
            },
            scales: {
                y: {
                    ticks: {
                        font: { family: "'Inter', sans-serif" },
                        callback: (value) => 'KES ' + value.toLocaleString()
                    },
                    grid: { color: BRAND.gridColor }
                },
                x: {
                    ticks: { font: { family: "'Inter', sans-serif" } },
                    grid: { display: false }
                }
            }
        }
    };

    // 5. Render
    new Chart(ctx, config);
});
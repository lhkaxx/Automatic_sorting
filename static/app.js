/**
 * 考场自动排座系统 — 前端交互增强
 */

document.addEventListener('DOMContentLoaded', function () {
    initSeatTooltips();
    initExportButtons();
});

/**
 * 座位 tooltip：hover 时显示完整信息
 */
function initSeatTooltips() {
    const tooltip = document.createElement('div');
    tooltip.className = 'seat-tooltip';
    tooltip.style.cssText = `
        position: fixed;
        background: #333;
        color: #fff;
        padding: 10px 14px;
        border-radius: 6px;
        font-size: 13px;
        pointer-events: none;
        z-index: 9999;
        display: none;
        max-width: 280px;
        line-height: 1.5;
        box-shadow: 0 4px 12px rgba(0,0,0,0.3);
    `;
    document.body.appendChild(tooltip);

    document.querySelectorAll('.seat-occupied').forEach(cell => {
        const title = cell.getAttribute('title');
        if (!title) return;

        cell.addEventListener('mouseenter', function (e) {
            tooltip.textContent = title;
            tooltip.style.display = 'block';
            positionTooltip(e, tooltip);
        });

        cell.addEventListener('mousemove', function (e) {
            positionTooltip(e, tooltip);
        });

        cell.addEventListener('mouseleave', function () {
            tooltip.style.display = 'none';
        });
    });
}

function positionTooltip(e, tooltip) {
    let x = e.clientX + 14;
    let y = e.clientY - 10;
    const rect = tooltip.getBoundingClientRect();
    if (x + rect.width > window.innerWidth - 10) {
        x = e.clientX - rect.width - 14;
    }
    if (y + rect.height > window.innerHeight - 10) {
        y = e.clientY - rect.height - 10;
    }
    if (x < 10) x = 10;
    if (y < 10) y = 10;
    tooltip.style.left = x + 'px';
    tooltip.style.top = y + 'px';
}

/**
 * 导出按钮处理
 */
function initExportButtons() {
    document.querySelectorAll('.btn-export').forEach(btn => {
        btn.addEventListener('click', function (e) {
            const format = this.dataset.format;
            if (format === 'csv') {
                window.location.href = '/export/csv';
            } else if (format === 'json') {
                window.location.href = '/export/json';
            }
        });
    });
}

/**
 * 班级筛选器（在 result_class 页面使用）
 */
function filterByClass(className) {
    document.querySelectorAll('.seat-occupied').forEach(cell => {
        const cellClass = cell.dataset.class || '';
        if (!className || cellClass === className) {
            cell.style.opacity = '1';
        } else {
            cell.style.opacity = '0.15';
        }
    });
}

async function renderChart(canvasId, endpoint, labelKey, datasetLabel, color) {
    const canvas = document.getElementById(canvasId);
    if (!canvas) return;

    try {
        const response = await fetch(endpoint);
        const data = await response.json();

        const labels = data.map((item) => item[labelKey]);
        const totals = data.map((item) => item.total);

        new Chart(canvas, {
            type: "bar",
            data: {
                labels,
                datasets: [
                    {
                        label: datasetLabel,
                        data: totals,
                        borderWidth: 1,
                        backgroundColor: color,
                    },
                ],
            },
            options: {
                responsive: true,
                scales: {
                    y: {
                        beginAtZero: false,
                    },
                },
            },
        });
    } catch (error) {
        console.error("Không thể tải dữ liệu biểu đồ:", error);
    }
}

document.addEventListener("DOMContentLoaded", () => {
    renderChart(
        "weeklyChart",
        "/stats/weekly",
        "week",
        "Dòng tiền ròng theo tuần (+ thu / - chi)",
        "rgba(16, 185, 129, 0.7)"
    );
    renderChart(
        "monthlyChart",
        "/stats/monthly",
        "month",
        "Dòng tiền ròng theo tháng (+ thu / - chi)",
        "rgba(37, 99, 235, 0.7)"
    );
});

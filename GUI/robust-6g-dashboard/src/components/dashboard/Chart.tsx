import React from "react";
import {
  CategoryScale,
  Chart as ChartJS,
  Legend,
  LineElement,
  LinearScale,
  PointElement,
  Tooltip,
  type ChartData,
  type ChartOptions,
} from "chart.js";
import { Line } from "react-chartjs-2";

ChartJS.register(
  CategoryScale,
  LinearScale,
  PointElement,
  LineElement,
  Tooltip,
  Legend,
);

type LineChartData = ChartData<"line", number[], string>;

interface DashboardChartProps {
  data?: LineChartData;
  options?: ChartOptions<"line">;
}

const DEFAULT_CHART_DATA: LineChartData = {
  labels: ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"],
  datasets: [
    {
      label: "Network Events",
      data: [14, 21, 18, 27, 24, 16, 19],
      borderColor: "#2563eb",
      backgroundColor: "rgba(37, 99, 235, 0.2)",
      tension: 0.3,
    },
  ],
};

/** """Renders a line chart with safe defaults for dashboard analytics.""" */
const Chart: React.FC<DashboardChartProps> = ({ data, options }) => {
  const finalData = data ?? DEFAULT_CHART_DATA;

  return (
    <div className="chart-container">
      <Line data={finalData} options={options} />
    </div>
  );
};

export default Chart;

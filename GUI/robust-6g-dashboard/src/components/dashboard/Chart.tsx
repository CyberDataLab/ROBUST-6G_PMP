import React from 'react';
import { Line } from 'react-chartjs-2';

const Chart: React.FC<{ data: any; options?: any }> = ({ data, options }) => {
    return (
        <div className="chart-container">
            <Line data={data} options={options} />
        </div>
    );
};

export default Chart;
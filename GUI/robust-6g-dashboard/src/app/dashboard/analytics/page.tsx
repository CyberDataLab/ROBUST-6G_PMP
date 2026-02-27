import React from 'react';
import StatsCard from '@/components/dashboard/StatsCard';
import Chart from '@/components/dashboard/Chart';
import UserTable from '@/components/dashboard/UserTable';

const AnalyticsPage: React.FC = () => {
    return (
        <div className="p-4">
            <h1 className="text-2xl font-bold mb-4">Analytics Overview</h1>
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4 mb-4">
                <StatsCard title="Total Users" value={100} />
                <StatsCard title="Active Sessions" value={75} />
            </div>
            <div className="mb-4">
                <Chart />
            </div>
            <div>
                <h2 className="text-xl font-semibold mb-2">User Activity</h2>
                <UserTable />
            </div>
        </div>
    );
};

export default AnalyticsPage;
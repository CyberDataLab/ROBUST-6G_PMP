import React from 'react';

interface StatsCardProps {
  title: string;
  value: number | string;
  icon: React.ReactNode;
  description?: string;
}

const StatsCard: React.FC<StatsCardProps> = ({ title, value, icon, description }) => {
  return (
    <div className="bg-white shadow-md rounded-lg p-4 flex items-center">
      <div className="mr-4 text-blue-500">
        {icon}
      </div>
      <div>
        <h2 className="text-lg font-semibold">{title}</h2>
        <p className="text-2xl font-bold">{value}</p>
        {description && <p className="text-gray-600">{description}</p>}
      </div>
    </div>
  );
};

export default StatsCard;
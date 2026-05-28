import React from "react";

interface StatsCardProps {
  title: string;
  value: number | string;
  icon?: React.ReactNode;
  description?: string;
}

/** """Displays a compact metric card with an optional icon and supporting text.""" */
const StatsCard: React.FC<StatsCardProps> = ({
  title,
  value,
  icon,
  description,
}) => {
  return (
    <div className="flex items-center rounded-lg bg-white p-4 shadow-md">
      {icon ? <div className="mr-4 text-blue-500">{icon}</div> : null}
      <div>
        <h2 className="text-lg font-semibold">{title}</h2>
        <p className="text-2xl font-bold">{value}</p>
        {description ? <p className="text-gray-600">{description}</p> : null}
      </div>
    </div>
  );
};

export default StatsCard;

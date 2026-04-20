import React from 'react';

interface TableProps {
  headers: string[];
  data: Array<Record<string, any>>;
}

const Table: React.FC<TableProps> = ({ headers, data }) => {
  return (
    <table className="min-w-full border-collapse border border-gray-200">
      <thead>
        <tr>
          {headers.map((header, index) => (
            <th key={index} className="border border-gray-200 px-4 py-2 text-left">
              {header}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {data.map((row, rowIndex) => (
          <tr key={rowIndex} className="hover:bg-gray-100">
            {headers.map((header, colIndex) => (
              <td key={colIndex} className="border border-gray-200 px-4 py-2">
                {row[header]}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
};

export default Table;
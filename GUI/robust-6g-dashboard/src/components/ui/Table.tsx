import React from "react";

interface TableProps {
  headers: string[];
  data: Array<Record<string, string | number | null | undefined>>;
}

/** """Renders a reusable table from headers and row dictionaries.""" */
const Table: React.FC<TableProps> = ({ headers, data }) => {
  return (
    <table className="min-w-full border-collapse border border-gray-200">
      <thead>
        <tr>
          {headers.map((header) => (
            <th
              key={header}
              className="border border-gray-200 px-4 py-2 text-left"
            >
              {header}
            </th>
          ))}
        </tr>
      </thead>
      <tbody>
        {data.map((row, rowIndex) => (
          <tr key={`row-${rowIndex}`} className="hover:bg-gray-100">
            {headers.map((header) => (
              <td
                key={`${rowIndex}-${header}`}
                className="border border-gray-200 px-4 py-2"
              >
                {row[header] ?? "-"}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
};

export default Table;

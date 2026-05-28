import React from "react";
import Table from "../ui/Table";

interface UserItem {
  id: string;
  name: string;
  email: string;
  role: string;
}

interface UserTableProps {
  users?: UserItem[];
}

const USER_TABLE_HEADERS = ["ID", "Name", "Email", "Role"];

/** """Transforms API user entities into the generic table row format.""" */
function mapUsersToRows(users: UserItem[]): Array<Record<string, string>> {
  return users.map((user) => {
    return {
      ID: user.id,
      Name: user.name,
      Email: user.email,
      Role: user.role,
    };
  });
}

/** """Displays a users table using pre-fetched data from parent components.""" */
const UserTable: React.FC<UserTableProps> = ({ users = [] }) => {
  const data = mapUsersToRows(users);

  return <Table headers={USER_TABLE_HEADERS} data={data} />;
};

export default UserTable;

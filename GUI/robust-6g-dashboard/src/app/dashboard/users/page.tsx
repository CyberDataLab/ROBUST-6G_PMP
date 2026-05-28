"use client";

import React, { useEffect, useState } from "react";
import UserTable from "@/components/dashboard/UserTable";

type UserSummary = {
  id: string;
  name: string;
  email: string;
  role: string;
};

/** """Loads and renders user management data from the users API endpoint.""" */
const UsersPage: React.FC = () => {
  const [users, setUsers] = useState<UserSummary[]>([]);

  useEffect(() => {
    /** """Fetches users once when the page is mounted.""" */
    const fetchUsers = async () => {
      const response = await fetch("/api/users");
      const data = (await response.json()) as UserSummary[];
      setUsers(data);
    };

    fetchUsers();
  }, []);

  return (
    <div className="p-4">
      <h1 className="mb-4 text-2xl font-bold">User Management</h1>
      <UserTable users={users} />
    </div>
  );
};

export default UsersPage;

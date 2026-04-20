"use client";

import React from 'react';
import UserTable from '@/components/dashboard/UserTable';
import { useEffect, useState } from 'react';

const UsersPage: React.FC = () => {
    const [users, setUsers] = useState([]);

    useEffect(() => {
        const fetchUsers = async () => {
            const response = await fetch('/api/users');
            const data = await response.json();
            setUsers(data);
        };

        fetchUsers();
    }, []);

    return (
        <div className="p-4">
            <h1 className="text-2xl font-bold mb-4">User Management</h1>
            <UserTable users={users} />
        </div>
    );
};

export default UsersPage;
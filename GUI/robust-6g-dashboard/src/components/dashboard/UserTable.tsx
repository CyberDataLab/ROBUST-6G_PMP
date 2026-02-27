import React from 'react';
import { useQuery } from 'react-query';
import { PrismaClient } from '@prisma/client';
import Table from '../ui/Table';

const prisma = new PrismaClient();

const UserTable: React.FC = () => {
  const { data: users, isLoading, error } = useQuery('users', async () => {
    return await prisma.user.findMany();
  });

  if (isLoading) return <div>Loading...</div>;
  if (error) return <div>Error loading users</div>;

  return (
    <Table>
      <thead>
        <tr>
          <th>ID</th>
          <th>Name</th>
          <th>Email</th>
          <th>Role</th>
        </tr>
      </thead>
      <tbody>
        {users.map(user => (
          <tr key={user.id}>
            <td>{user.id}</td>
            <td>{user.name}</td>
            <td>{user.email}</td>
            <td>{user.role}</td>
          </tr>
        ))}
      </tbody>
    </Table>
  );
};

export default UserTable;
export type User = {
  id: string;
  email: string;
  name: string;
  createdAt: Date;
  updatedAt: Date;
};

export type Organization = {
  id: string;
  name: string;
  allowedEmailDomains: string[];
  createdAt: Date;
  updatedAt: Date;
};

export type Dashboard = {
  id: string;
  organizationId: string;
  title: string;
  createdAt: Date;
  updatedAt: Date;
};

export type Report = {
  id: string;
  dashboardId: string;
  data: any; // Replace 'any' with a more specific type if known
  createdAt: Date;
  updatedAt: Date;
};

export type AuditLog = {
  id: string;
  action: string;
  userId: string;
  createdAt: Date;
};
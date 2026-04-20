# robust-6g-dashboard

## Overview

The Robust 6G Dashboard is an enterprise-level application built with **Next.js 14+ (App Router)**, **TypeScript**, **Prisma ORM 7.x**, and **PostgreSQL**. It provides a comprehensive dashboard for managing users, viewing analytics, and configuring settings, all while adhering to a strict **email domain affiliation policy** for the organization **"robust-6g"**.

---

## Tech Stack

| Layer          | Technology                                      |
| -------------- | ----------------------------------------------- |
| Framework      | Next.js 14+ (App Router)                        |
| Language       | TypeScript                                      |
| Styling        | Tailwind CSS + shadcn/ui + lucide-react         |
| Auth           | Auth.js (NextAuth) – Credentials Provider       |
| Database       | PostgreSQL                                      |
| ORM            | Prisma ORM 7.x (Driver Adapter: `@prisma/adapter-pg`) |
| Validation     | Zod                                             |
| Data Fetching  | TanStack Query                                  |
| Password Hash  | bcrypt                                          |
| Access Control | Next.js Middleware (role-based)                  |

---

## Features

- **Authentication** – Email + password login via Auth.js Credentials Provider
- **Role-based access control** – `ADMIN` and `ANALYST` roles enforced by middleware
- **Organization isolation** – All data queries scoped to the user's `organizationId`
- **Email domain affiliation** – Users can only be created/login with emails matching allowed domains
- **Dashboard management** – ADMIN can activate/load external dashboards; ANALYST can view active ones
- **Audit logging** – All admin actions are recorded in `AuditLog`
- **BFF architecture** – Browser never calls external APIs directly; all proxied through `/api/*`

---

## Prerequisites

Before starting, ensure you have the following installed on your Mac:

### 1. Node.js (v18 or higher)

```bash
# Check if installed
node --version

# Install via Homebrew (if not installed)
brew install node@20
```

### 2. pnpm (recommended) or npm

```bash
# Install pnpm globally
npm install -g pnpm

# Verify
pnpm --version
```

### 3. PostgreSQL (v14 or higher)

```bash
# Install via Homebrew
brew install postgresql@16

# Start PostgreSQL service
brew services start postgresql@16

# Verify it's running
pg_isready
```

---

## Installation (Step by Step from Scratch)

### Step 1 – Clone the repository

```bash
git clone https://github.com/yourusername/robust-6g-dashboard.git
cd robust-6g-dashboard
```

### Step 2 – Install all dependencies

```bash
pnpm install
```

This installs all required packages defined in `package.json`, including:

| Package                    | Purpose                                  |
| -------------------------- | ---------------------------------------- |
| `next`                     | Framework                                |
| `react`, `react-dom`       | UI library                               |
| `typescript`               | Type safety                              |
| `tailwindcss`              | Utility-first CSS                        |
| `@shadcn/ui`               | UI component library                     |
| `lucide-react`             | Icon library                             |
| `next-auth`                | Authentication                           |
| `prisma`                   | ORM CLI (devDependency)                  |
| `@prisma/client`           | Prisma Client runtime                    |
| `@prisma/adapter-pg`       | Prisma PostgreSQL driver adapter         |
| `pg`                       | Node.js PostgreSQL driver                |
| `zod`                      | Schema validation                        |
| `@tanstack/react-query`    | Server state management                  |
| `bcrypt` + `@types/bcrypt` | Password hashing                         |
| `dotenv`                   | Environment variable loading             |
| `tsx`                      | TypeScript execution (for seed scripts)  |

> **Note:** All packages listed above are required for `pnpm prisma db seed` to work correctly.
> The seed script (`prisma/seed.ts`) depends on `@prisma/adapter-pg`, `pg`, `bcrypt`, `dotenv`, and `tsx`.

If `package.json` is incomplete or you need to add packages individually:

```bash
# Core framework
pnpm add next react react-dom
pnpm add -D typescript @types/react @types/react-dom @types/node

# Styling & UI
pnpm add tailwindcss postcss autoprefixer
pnpm add lucide-react class-variance-authority clsx tailwind-merge

# Auth
pnpm add next-auth

# Database (required for Prisma Client + seed)
pnpm add @prisma/client @prisma/adapter-pg pg
pnpm add -D prisma @types/pg

# Validation & Data fetching
pnpm add zod @tanstack/react-query

# Password hashing (required for seed)
pnpm add bcrypt
pnpm add -D @types/bcrypt

# Environment variables (required for prisma.config.ts)
pnpm add dotenv

# TypeScript runner (required for seed command)
pnpm add -D tsx
```

### Step 3 – Create the PostgreSQL database and user

Open a terminal and connect to PostgreSQL:

```bash
# Connect as default superuser
psql postgres
```

Then run the following SQL commands inside the `psql` shell:

```sql
-- Create a dedicated user with CREATEDB permission (change password as desired)
-- CREATEDB is required by Prisma Migrate to create a temporary shadow database
CREATE USER robust6g_admin WITH PASSWORD 'your_secure_password_here' CREATEDB;

-- Create the database
CREATE DATABASE robust6g_dashboard OWNER robust6g_admin;

-- Grant all privileges
GRANT ALL PRIVILEGES ON DATABASE robust6g_dashboard TO robust6g_admin;

-- Exit psql
\q
```

> **Verify** the database was created:
> ```bash
> psql -U robust6g_admin -d robust6g_dashboard -h localhost
> # You should connect successfully. Type \q to exit.
> ```

### Step 4 – Configure environment variables

```bash
# Copy the example file
cp .env.example .env
```

Edit `.env` with your actual values:

```env
# Database connection
DATABASE_URL="postgresql://robust6g_admin:your_secure_password_here@localhost:5432/robust6g_dashboard?schema=public"

# Auth.js secret (generate a random string)
# You can generate one with: openssl rand -base64 32
NEXTAUTH_SECRET="your-generated-secret-here"
NEXTAUTH_URL="http://localhost:3000"

# External API (for BFF proxy)
EXTERNAL_API_BASE_URL="https://api.example.com"
EXTERNAL_API_TOKEN="your-external-api-token"
```

To generate `NEXTAUTH_SECRET`:

```bash
openssl rand -base64 32
```

Copy the output and paste it as the value.

### Step 5 – Generate Prisma Client

Prisma 7.x uses `prisma.config.ts` instead of `url` in `schema.prisma`:

```bash
# Generate the Prisma Client (reads prisma.config.ts for datasource URL)
pnpm prisma generate
```

### Step 6 – Run database migrations

```bash
# Create and apply all migrations
pnpm prisma migrate dev --name init
```

This will:
1. Read `prisma/schema.prisma` for the data model
2. Read `prisma.config.ts` for the database URL
3. Create the migration SQL files in `prisma/migrations/`
4. Apply them to your PostgreSQL database
5. Create all tables: `Organization`, `User`, `Dashboard`, `Report`, `AuditLog`

### Step 7 – Seed the database

```bash
pnpm prisma db seed
```

This runs `prisma/seed.ts` which creates:

| Resource           | Details                                                    |
| ------------------ | ---------------------------------------------------------- |
| **Organization**   | `robust-6g` with allowed domains `["robust-6g.eu", "robust-6g.org"]` |
| **Admin user**     | `admin@robust-6g.eu` / password: `Admin123!` / role: `ADMIN`  |
| **Analyst user**   | `analyst@robust-6g.eu` / password: `Analyst123!` / role: `ANALYST` |
| **Sample dashboard** | An `ACTIVE` dashboard linked to `robust-6g`              |

> ⚠️ **Change default passwords** before deploying to any non-local environment.

### Step 8 – Start the development server

```bash
pnpm dev
```

The application will be available at **http://localhost:3000**.

### Step 9 – Verify everything works

1. Open **http://localhost:3000** – you should see the login page
2. Log in with `admin@robust-6g.eu` / `Admin123!`
3. You should land on the dashboard with the organization name "robust-6g" in the header
4. Navigate to **Users** to manage users (ADMIN only)
5. Try creating a user with a non-affiliated email (e.g., `user@gmail.com`) – it should be rejected

---

## Email Domain Affiliation Policy (robust-6g)

### How It Works

The system enforces **mandatory organizational affiliation** based on email domains. Every user must belong to an organization, and their email must match one of the organization's allowed domains.

### Where Domains Are Defined

Allowed email domains are stored in the `Organization.allowedEmailDomains` field (a `String[]` in PostgreSQL). For the `robust-6g` organization, these are set during seeding:

```typescript
// prisma/seed.ts
allowedEmailDomains: ["robust-6g.eu", "robust-6g.org"]
```

To add or remove allowed domains, update the organization record in the database or modify the seed file.

### Validation at User Creation (ADMIN → `/api/admin/users`)

When an ADMIN creates a new user:

1. The system loads the ADMIN's organization (from session `organizationId`)
2. Extracts the domain from the new user's email
3. Checks if that domain is in `Organization.allowedEmailDomains`
4. If **not allowed** → returns `400 Bad Request`:
   ```json
   {
     "error": "Email domain 'gmail.com' is not allowed for organization 'robust-6g'. Allowed domains: robust-6g.eu, robust-6g.org"
   }
   ```
5. If **allowed** → creates the user with the ADMIN's `organizationId`

### Validation at Login (Auth.js `authorize()`)

When a user tries to log in:

1. Looks up the user by email in the database
2. Verifies the password with bcrypt
3. Loads the user's organization
4. Extracts the email domain and checks it against `allowedEmailDomains`
5. If **not affiliated** → rejects with: `"Not affiliated / invalid organization email domain"`

### Examples

| Email                        | Domain          | Allowed? | Reason                              |
| ---------------------------- | --------------- | -------- | ----------------------------------- |
| `maria@robust-6g.eu`        | `robust-6g.eu`  | ✅ Yes   | Domain in allowed list              |
| `carlos@robust-6g.org`      | `robust-6g.org` | ✅ Yes   | Domain in allowed list              |
| `admin@robust-6g.eu`        | `robust-6g.eu`  | ✅ Yes   | Domain in allowed list              |
| `user@gmail.com`            | `gmail.com`     | ❌ No    | Domain not in allowed list          |
| `test@robust-6g.com`        | `robust-6g.com` | ❌ No    | `.com` is not in allowed list       |
| `hacker@other-org.eu`       | `other-org.eu`  | ❌ No    | Domain belongs to different org     |

### Helper Functions (`src/lib/org.ts`)

```typescript
extractDomain(email: string): string
// "admin@robust-6g.eu" → "robust-6g.eu"

isEmailAllowedForOrg(email: string, org: Organization): boolean
// Checks if email domain is in org.allowedEmailDomains

findOrganizationByEmailDomain(domain: string): Promise<Organization | null>
// Queries DB for org where allowedEmailDomains contains the domain
```

---

## Key Files Reference

```
├── prisma/
│   ├── schema.prisma          # Data model (no url in datasource)
│   ├── seed.ts                # Seeds robust-6g org + default users
│   └── migrations/            # Auto-generated migrations
├── prisma.config.ts           # Prisma 7.x datasource config
├── src/
│   ├── lib/
│   │   ├── db.ts              # PrismaClient singleton with driver adapter
│   │   ├── org.ts             # Organization helpers (domain validation)
│   │   └── auth.ts            # Auth.js config (Credentials Provider)
│   ├── middleware.ts          # Role-based route protection
│   ├── app/
│   │   ├── api/
│   │   │   ├── auth/[...nextauth]/route.ts
│   │   │   ├── admin/users/route.ts          # POST (create user)
│   │   │   ├── admin/users/[id]/route.ts     # PATCH, DELETE
│   │   │   └── dashboards/route.ts
│   │   ├── (auth)/login/page.tsx
│   │   ├── dashboard/page.tsx
│   │   └── admin/users/page.tsx
│   └── components/
│       ├── ui/                # shadcn/ui components
│       └── layout/            # Header, Sidebar
└── .env.example
```

---

## Available Scripts

| Command                         | Description                              |
| ------------------------------- | ---------------------------------------- |
| `pnpm dev`                      | Start development server (port 3000)     |
| `pnpm build`                    | Build for production                     |
| `pnpm start`                    | Start production server                  |
| `pnpm lint`                     | Run ESLint                               |
| `pnpm prisma generate`         | Generate Prisma Client                   |
| `pnpm prisma migrate dev`      | Run migrations in development            |
| `pnpm prisma migrate deploy`   | Run migrations in production             |
| `pnpm prisma db seed`          | Seed the database                        |
| `pnpm prisma studio`           | Open Prisma Studio (visual DB browser)   |
| `pnpm test`                    | Run test suite                           |

---

## Troubleshooting

### PostgreSQL connection refused

```bash
# Check if PostgreSQL is running
brew services list | grep postgresql

# Restart if needed
brew services restart postgresql@16
```

### "role does not exist" error

```bash
# Create the user manually
psql postgres -c "CREATE USER robust6g_admin WITH PASSWORD 'your_secure_password_here';"
```

### Prisma migration fails

```bash
# Reset the database (WARNING: deletes all data)
pnpm prisma migrate reset

# Then re-seed
pnpm prisma db seed
```

### "NEXTAUTH_SECRET missing" error

```bash
# Generate and set it
echo "NEXTAUTH_SECRET=$(openssl rand -base64 32)" >> .env
```

### Port 3000 already in use

```bash
# Find and kill the process
lsof -ti:3000 | xargs kill -9

# Or run on a different port
pnpm dev -- -p 3001
```

---

## Production Deployment

For production deployment:

1. Set all environment variables on your hosting platform
2. Run migrations: `pnpm prisma migrate deploy`
3. Build: `pnpm build`
4. Start: `pnpm start`

> ⚠️ Never use `migrate dev` in production. Always use `migrate deploy`.

---

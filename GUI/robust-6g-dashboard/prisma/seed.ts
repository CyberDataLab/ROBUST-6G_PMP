import { PrismaClient } from "@prisma/client";
import { PrismaPg } from "@prisma/adapter-pg";
import bcrypt from "bcrypt";

const adapter = new PrismaPg({ connectionString: process.env.DATABASE_URL! });
const prisma = new PrismaClient({ adapter });

async function main() {
  console.log("🌱 Seeding database...");

  // 1. Create organization robust-6g
  const org = await prisma.organization.upsert({
    where: { slug: "robust-6g" },
    update: {},
    create: {
      name: "robust-6g",
      slug: "robust-6g",
      allowedEmailDomains: ["robust-6g.eu", "robust-6g.org"],
    },
  });
  console.log(`✅ Organization created: ${org.name} (${org.id})`);

  // 2. Create ADMIN user
  const adminPasswordHash = await bcrypt.hash("Admin123!", 12);
  const admin = await prisma.user.upsert({
    where: { email: "admin@robust-6g.eu" },
    update: {},
    create: {
      name: "Admin User",
      email: "admin@robust-6g.eu",
      passwordHash: adminPasswordHash,
      role: "ADMIN",
      organizationId: org.id,
    },
  });
  console.log(`✅ Admin user created: ${admin.email}`);

  // 3. Create USER user
  const userPasswordHash = await bcrypt.hash("User123!", 12);
  const user = await prisma.user.upsert({
    where: { email: "user@robust-6g.eu" },
    update: {},
    create: {
      name: "User",
      email: "user@robust-6g.eu",
      passwordHash: userPasswordHash,
      role: "ANALYST",
      organizationId: org.id,
    },
  });
  console.log(`✅ User created: ${user.email}`);

  // 4. Create sample dashboard
  const dashboard = await prisma.dashboard.upsert({
    where: {
      externalId_organizationId: {
        externalId: "ext-dashboard-001",
        organizationId: org.id,
      },
    },
    update: {},
    create: {
      name: "Network Performance Overview",
      externalId: "ext-dashboard-001",
      status: "ACTIVE",
      iframeUrl: "https://api.example.com/dashboards/ext-dashboard-001/embed",
      organizationId: org.id,
    },
  });
  console.log(`✅ Dashboard created: ${dashboard.name}`);

  console.log("🌱 Seeding complete!");
}

main()
  .catch((e) => {
    console.error("❌ Seed error:", e);
    process.exit(1);
  })
  .finally(async () => {
    await prisma.$disconnect();
  });

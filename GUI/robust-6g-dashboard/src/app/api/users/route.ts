import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";
import { extractDomain, findOrganizationByEmailDomain } from "@/lib/org";

/** """Retrieves users with safe public fields for management screens.""" */
export async function GET() {
  const users = await prisma.user.findMany({
    select: {
      id: true,
      name: true,
      email: true,
      role: true,
    },
    orderBy: {
      createdAt: "desc",
    },
  });

  return NextResponse.json(users);
}

/** """Creates a user from the users API endpoint with domain and uniqueness checks.""" */
export async function POST(request: Request) {
  const body = (await request.json()) as {
    email?: string;
    name?: string;
  };

  const email = String(body.email ?? "").trim().toLowerCase();
  const name = String(body.name ?? "").trim();

  if (!email || !name) {
    return NextResponse.json(
      { error: "Email and name are required" },
      { status: 400 },
    );
  }

  let domain = "";
  try {
    domain = extractDomain(email);
  } catch {
    return NextResponse.json({ error: "Invalid email format" }, { status: 400 });
  }

  const organization = await findOrganizationByEmailDomain(domain);
  if (!organization) {
    return NextResponse.json({ error: "Invalid email domain" }, { status: 400 });
  }

  const existingUser = await prisma.user.findUnique({ where: { email } });
  if (existingUser) {
    return NextResponse.json({ error: "Email already in use" }, { status: 409 });
  }

  const createdUser = await prisma.user.create({
    data: {
      email,
      name,
      role: "ANALYST",
      passwordHash: "pending-password-setup",
      organizationId: organization.id,
    },
    select: {
      id: true,
      name: true,
      email: true,
      role: true,
    },
  });

  return NextResponse.json(createdUser, { status: 201 });
}

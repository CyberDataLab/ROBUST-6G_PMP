import { NextResponse } from "next/server";
import { Prisma, Role } from "@prisma/client";
import bcrypt from "bcrypt";
import { prisma } from "@/lib/db";
import { extractDomain, findOrganizationByEmailDomain } from "@/lib/org";

const ALLOWED_UI_ROLES = ["ADMIN", "USER"] as const;
type UiRole = (typeof ALLOWED_UI_ROLES)[number];

export async function POST(request: Request) {
  try {
    const body = await request.json();
    const email = String(body?.email ?? "").trim().toLowerCase();
    const password = String(body?.password ?? "");
    const requestedRole = String(body?.role ?? "")
      .trim()
      .toUpperCase() as UiRole;

    if (!email || !password || !requestedRole) {
      return NextResponse.json(
        { error: "Email, password and role are required" },
        { status: 400 },
      );
    }

    if (!ALLOWED_UI_ROLES.includes(requestedRole)) {
      return NextResponse.json(
        { error: "Invalid role. Allowed roles: admin, user" },
        { status: 400 },
      );
    }

    // Keep DB compatibility: UI "USER" maps to persisted "ANALYST".
    const persistedRole: Role =
      requestedRole === "USER" ? "ANALYST" : "ADMIN";

    let domain: string;
    try {
      domain = extractDomain(email);
    } catch {
      return NextResponse.json({ error: "Invalid email format" }, { status: 400 });
    }

    const organization = await findOrganizationByEmailDomain(domain);
    if (!organization) {
      return NextResponse.json(
        { error: "Email domain is not allowed for any organization" },
        { status: 403 },
      );
    }

    const existingUser = await prisma.user.findUnique({
      where: { email },
    });
    if (existingUser) {
      return NextResponse.json({ error: "User already exists" }, { status: 409 });
    }

    const passwordHash = await bcrypt.hash(password, 12);
    const defaultName = email.split("@")[0];

    const createdUser = await prisma.user.create({
      data: {
        name: defaultName,
        email,
        passwordHash,
        role: persistedRole,
        organizationId: organization.id,
      },
      select: {
        id: true,
        name: true,
        email: true,
        role: true,
        organizationId: true,
        createdAt: true,
      },
    });

    return NextResponse.json({ user: createdUser }, { status: 201 });
  } catch (error) {
    if (
      error instanceof Prisma.PrismaClientKnownRequestError &&
      error.code === "P2002"
    ) {
      return NextResponse.json({ error: "User already exists" }, { status: 409 });
    }

    return NextResponse.json(
      { error: "Registration failed. Please try again." },
      { status: 500 },
    );
  }
}

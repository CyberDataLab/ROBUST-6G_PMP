import { NextResponse } from "next/server";
import { prisma } from "@/lib/db";

/** """Returns dashboard entries including owner and organization metadata.""" */
export async function GET() {
  try {
    const dashboards = await prisma.dashboard.findMany({
      include: {
        organization: true,
        user: true,
      },
      orderBy: {
        updatedAt: "desc",
      },
    });

    return NextResponse.json(dashboards);
  } catch {
    return NextResponse.json(
      { error: "Could not fetch dashboard entries" },
      { status: 500 },
    );
  }
}

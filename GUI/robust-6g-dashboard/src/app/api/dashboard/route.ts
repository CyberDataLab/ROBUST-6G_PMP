import { NextResponse } from 'next/server';
import { prisma } from '@/lib/prisma';

export async function GET() {
    try {
        const dashboardData = await prisma.dashboard.findMany();
        return NextResponse.json(dashboardData);
    } catch (error) {
        return NextResponse.error();
    }
}

export async function POST(request: Request) {
    const data = await request.json();
    
    try {
        const newDashboardEntry = await prisma.dashboard.create({
            data: {
                title: data.title,
                content: data.content,
                // Add other fields as necessary
            },
        });
        return NextResponse.json(newDashboardEntry, { status: 201 });
    } catch (error) {
        return NextResponse.error();
    }
}
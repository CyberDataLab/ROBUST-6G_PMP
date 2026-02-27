import "next-auth";

declare module "next-auth" {
  interface User {
    role: "ADMIN" | "ANALYST";
    organizationId: string;
    organizationSlug: string;
  }

  interface Session {
    user: {
      id: string;
      role: "ADMIN" | "ANALYST";
      organizationId: string;
      organizationSlug: string;
      name?: string | null;
      email?: string | null;
      image?: string | null;
    };
  }
}

declare module "next-auth/jwt" {
  interface JWT {
    id: string;
    role: "ADMIN" | "ANALYST";
    organizationId: string;
    organizationSlug: string;
  }
}
import "next-auth";

declare module "next-auth" {
  interface User {
    role: "ADMIN" | "USER";
    organizationId: string;
    organizationSlug: string;
  }

  interface Session {
    user: {
      id: string;
      role: "ADMIN" | "USER";
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
    role: "ADMIN" | "USER";
    organizationId: string;
    organizationSlug: string;
  }
}

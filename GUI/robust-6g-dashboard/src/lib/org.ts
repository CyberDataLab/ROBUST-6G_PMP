import { Organization } from "@prisma/client";
import { prisma } from "@/lib/db";

export function extractDomain(email: string): string {
  const parts = email.split("@");
  if (parts.length !== 2) {
    throw new Error(`Invalid email format: ${email}`);
  }
  return parts[1].toLowerCase();
}

export function isEmailAllowedForOrg(
  email: string,
  org: Organization
): boolean {
  const domain = extractDomain(email);
  return org.allowedEmailDomains.includes(domain);
}

export async function findOrganizationByEmailDomain(
  domain: string
): Promise<Organization | null> {
  const org = await prisma.organization.findFirst({
    where: {
      allowedEmailDomains: {
        has: domain.toLowerCase(),
      },
    },
  });
  return org;
}
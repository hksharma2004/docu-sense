import { ButtonLink, PageHeader } from "@/components/ui";

export default function NotFound() {
  return (
    <>
      <PageHeader title="Page Not Found" description="This document, version or page doesn’t exist." />
      <ButtonLink href="/" variant="primary">
        Browse Documents
      </ButtonLink>
    </>
  );
}

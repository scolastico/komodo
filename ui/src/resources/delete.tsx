import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { UsableResource } from ".";
import { usePermissions, useRead, useWrite } from "@/lib/hooks";
import { usableResourcePath } from "@/lib/utils";
import { Checkbox } from "@mantine/core";
import { ConfirmModal } from "mogh_ui";
import { ICONS } from "@/lib/icons";

export default function DeleteResource({
  type,
  id,
}: {
  type: UsableResource;
  id: string;
}) {
  const nav = useNavigate();
  const key = type === "ResourceSync" ? "sync" : type.toLowerCase();
  const { canWrite } = usePermissions({ type, id });
  const [keepContainers, setKeepContainers] = useState(false);
  const resource = useRead(`Get${type}`, {
    [key]: id,
  } as any).data;
  const { mutateAsync, isPending } = useWrite(`Delete${type}`, {
    onSuccess: () => nav(`/${usableResourcePath(type)}`),
  });

  if (!resource || !canWrite) return null;

  return (
    <ConfirmModal
      title={
        <>
          Confirm <b>Delete</b>
        </>
      }
      confirmButtonContent="Delete"
      icon={<ICONS.Delete size="1rem" />}
      targetNoIcon
      targetProps={{ w: "fit", px: "xs" }}
      confirmText={resource.name}
      additional={
        type === "Stack" ? (
          <Checkbox
            label="Keep containers running"
            description="Skips the stack destroy, leaving the containers orphaned from any Stack. Useful when transitioning to a git / file defined Stack."
            checked={keepContainers}
            onChange={(e) => setKeepContainers(e.currentTarget.checked)}
          />
        ) : undefined
      }
      onConfirm={() =>
        mutateAsync(
          type === "Stack"
            ? ({ id, keep_containers: keepContainers } as any)
            : { id }
        )
      }
      loading={isPending}
      confirmProps={{ variant: "filled", color: "red" }}
    >
      <ICONS.Delete size="1.3rem" />
    </ConfirmModal>
  );
}

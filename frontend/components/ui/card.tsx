/** Surface container. ~30 card-ish containers had drifted into 8 families
 *  across 10 paddings, 3 radii, and 6 different `bg-card` opacities. */

import { cn } from "@/lib/utils";

export function Card({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      {...props}
      className={cn("rounded-lg border border-border bg-card text-card-foreground p-4", className)}
    />
  );
}

export function CardHeader({ className, ...props }: React.ComponentProps<"div">) {
  return <div {...props} className={cn("mb-3 flex items-center gap-2", className)} />;
}

export function CardTitle({ className, ...props }: React.ComponentProps<"h3">) {
  return <h3 {...props} className={cn("text-sm font-semibold", className)} />;
}

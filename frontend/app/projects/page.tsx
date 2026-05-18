"use client";

import Link from "next/link";
import { motion, useReducedMotion } from "motion/react";
import { buttonVariants } from "@/components/ui/button";
import { useDocumentTitle } from "@/lib/use-document-title";

export default function ProjectsPage() {
  useDocumentTitle("Projects");
  const reduce = useReducedMotion();
  const fadeUp = reduce
    ? { initial: false, animate: { opacity: 1, y: 0 } }
    : {
        initial: { opacity: 0, y: 8 },
        animate: { opacity: 1, y: 0 },
        transition: { type: "spring" as const, stiffness: 320, damping: 32 },
      };

  return (
    <main id="main" className="flex flex-1 flex-col p-8 gap-8 max-w-5xl w-full mx-auto">
      <motion.header
        {...fadeUp}
        className="flex items-center justify-between"
      >
        <div className="flex items-center gap-3">
          <span className="text-2xl select-none" role="img" aria-label="Grove">
            🌳
          </span>
          <div>
            <p className="text-xs uppercase tracking-widest text-muted-foreground">
              DIG
            </p>
            <h1 className="text-2xl font-semibold tracking-tight">Projects</h1>
          </div>
        </div>
        <Link href="/pipelines" className={buttonVariants({ variant: "default" })}>
          <span className="mr-1.5">🛤</span> Open Pipelines instead
        </Link>
      </motion.header>

      <motion.section
        {...fadeUp}
        transition={{
          ...("transition" in fadeUp ? fadeUp.transition : {}),
          delay: 0.08,
        }}
        className="border border-dashed border-border rounded-xl p-12 flex flex-col items-center justify-center gap-4 text-center bg-muted/20"
      >
        <motion.div
          initial={reduce ? false : { scale: 0.7, opacity: 0, rotate: -8 }}
          animate={{ scale: 1, opacity: 1, rotate: 0 }}
          transition={{ type: "spring", stiffness: 220, damping: 16, delay: 0.18 }}
          className="text-7xl select-none"
          role="img"
          aria-label="Empty grove"
        >
          🪴
        </motion.div>
        <p className="text-sm text-muted-foreground max-w-md">
          No projects yet. Project creation, ingest, and the pipeline canvas
          arrive in <span className="font-medium text-foreground">Phase 1+</span>.
        </p>
        <Link href="/" className={buttonVariants({ variant: "ghost" })}>
          ← Back home
        </Link>
      </motion.section>
    </main>
  );
}

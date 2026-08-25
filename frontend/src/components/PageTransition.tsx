import { motion, useReducedMotion } from "framer-motion";
import type { ReactNode } from "react";

type PageTransitionProps = {
  children: ReactNode;
  className?: string;
};

const variants = {
  initial: { opacity: 0, y: 16, filter: "blur(4px)" },
  animate: { opacity: 1, y: 0, filter: "blur(0px)" },
  exit: { opacity: 0, y: -8, filter: "blur(2px)" },
};

export function PageTransition({ children, className }: PageTransitionProps) {
  const reducedMotion = useReducedMotion();
  return (
    <motion.div
      variants={variants}
      initial={reducedMotion ? false : "initial"}
      animate="animate"
      exit={reducedMotion ? undefined : "exit"}
      transition={reducedMotion ? { duration: 0 } : { duration: 0.35, ease: [0.23, 1, 0.32, 1] }}
      className={className}
    >
      {children}
    </motion.div>
  );
}

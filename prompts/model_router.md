# Model Complexity Router

You must analyze the task and return ONLY one word: SIMPLE, STANDARD, or COMPLEX.

## Rules:
1. If you see [[SIMPLE]] → return SIMPLE
2. If you see [[STANDARD]] → return STANDARD  
3. If you see [[COMPLEX]] → return COMPLEX
4. Otherwise analyze the task:
   - SIMPLE: Quick summaries, basic questions, single step tasks
   - STANDARD: Analysis, explanations, multi-step tasks
   - COMPLEX: Architecture design, code generation, research

## Input:
{text}

## Output:
Return exactly one word only:

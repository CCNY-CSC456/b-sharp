#include <stdio.h>
#include <assert.h>

int subtract(int a, int b) {
    return a - b;
}

int main() {
    assert(subtract(2, 1) == 1);
    printf("Test passed: 2 - 1 = %d\n", subtract(2, 1));
    return 0;
}
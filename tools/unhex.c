/* reverse "od -h" operation for Unix V6 */
/* written in pre-K&R C */

int ibuf[259];		/* struct buf */
int obuf[259];

main(argc,argv)
char **argv;
{
	int token, bytecnt;
	register int c;			/* char or read count */
	char sp, lastc, lasthi, nfirst;

	obuf[0] = 1;			/* standard output by default */
	if (argc>2) {
							/* create output file */
		if ((obuf[0] = creat(argv[2], 0666)) < 0) {
			diag(argv[2]);
			diag(": failed to create\n");
			return;
		}
	}
	if (argc>1 && fopen(argv[1], ibuf)>=0) {
		sp = 0;
		token = 0;
		bytecnt = 0;
		nfirst = 0;
		for(;;) {
			/* reading from file */
			c = getc(ibuf);
			if (c <= 0)
				break;
			/* decoding loop */
			if (c==' ' || c=='\n') {
				if (lastc!=' ' && lastc!='\n') {
					/* end of token */
					if (sp>0) {
						if (nfirst) putc(lasthi, obuf);
						putc(token & 0377, obuf);
						lasthi = token >> 8;
						nfirst = 1;
					} else {
						/* first token in the line */
						bytecnt = token;
					}
				}
				if (c==' ') sp++;
				else {
					/* new line */
					sp = 0;
				}
				token = 0;
			} else {
				/* actual hex and octal conversion */
				token = sp>0 ? (token<<4) : (token<<3);
				token =+ c<='9' ? c-'0' : c-'W';
			}
			lastc = c;
		}
		if (!(bytecnt & 1))
			putc(lasthi, obuf);

		fflush(obuf);
		close(ibuf[0]);
		close(obuf[0]);
	} else if (argc>1) {
		diag(argv[1]);
		diag(": cannot open\n");
	} else {
		diag("error: filename missing\n");
	}
}

diag(s)
char *s;
{
	while(*s)
		write(2,s++,1);
}

